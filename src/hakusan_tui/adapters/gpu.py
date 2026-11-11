"""GRES / TRES から GPU 割当状況を計算する。

- 割当はSlurm上の値。実使用率（利用率・VRAM）はここでは扱わない。
- MIG・仮想分割GPUは物理GPUと別単位で集計し、物理GPU枚数に加算しない。
- ノードは名前で一意化し、複数パーティション所属でも重複集計しない。
- 総数・割当数のどちらかが不明なら空き数は ``None``。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from hakusan_tui.models import GpuAllocation, GpuGroupSummary, Node

PHYSICAL_GPU_TYPES = ("a40", "a100", "h100", "h200", "v100", "l40", "l40s", "a6000", "rtx")
_MIG_PATTERN = re.compile(r"(\d+g\.\d+gb|mig)", re.IGNORECASE)
_FRACTION_PATTERN = re.compile(r"(vgpu|frac|quarter|1_4|1/4|_q\b)", re.IGNORECASE)


@dataclass(frozen=True)
class GresEntry:
    name: str
    gpu_type: str | None
    count: int | None


def parse_gres(text: str | None) -> list[GresEntry]:
    """``gpu:a40:2(S:0-1),gpu:2`` → GresEntry のリスト。"""
    if not text:
        return []
    entries = []
    for item in _split_gres_items(text):
        entry = _parse_gres_item(item)
        if entry is not None:
            entries.append(entry)
    return entries


def _split_gres_items(text: str) -> list[str]:
    # 括弧内のカンマ（IDX:0,2 など）では区切らない
    items, depth, current = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += ch
    items.append(current)
    return [i.strip() for i in items if i.strip()]


def _parse_gres_item(item: str) -> GresEntry | None:
    body = item.split("(", 1)[0]
    parts = body.split(":")
    if not parts or not parts[0]:
        return None
    name = parts[0]
    if len(parts) == 1:
        return GresEntry(name, None, 1)
    if len(parts) == 2:
        return GresEntry(name, None, _to_int(parts[1])) if parts[1].isdigit() else GresEntry(
            name, parts[1], 1
        )
    return GresEntry(name, parts[1], _to_int(parts[2]))


def _to_int(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def classify_unit(gpu_type: str | None) -> str:
    if not gpu_type:
        return "unknown"
    if _MIG_PATTERN.search(gpu_type):
        return "mig_instance"
    if _FRACTION_PATTERN.search(gpu_type):
        return "virtual_fraction"
    lowered = gpu_type.lower()
    if any(lowered.startswith(t) for t in PHYSICAL_GPU_TYPES):
        return "physical_gpu"
    return "unknown"


def classify_group(gpu_type: str | None, node_name: str, unit: str) -> str:
    text = f"{gpu_type or ''} {node_name}".lower()
    if "h100" in text:
        return "H100 VM" if unit == "virtual_fraction" else "H100"
    if "a100" in text:
        return "A100"
    if "a40" in text:
        return "A40"
    return generic_group_label(gpu_type, unit)


def generic_group_label(gpu_type: str | None, unit: str) -> str:
    """HAKUSAN 以外の型は Slurm の type 名をそのまま見出しにする（例 ``v100`` → ``V100``）。"""
    if not gpu_type:
        return "不明"
    label = gpu_type.upper()
    # MIG・分割GPUは物理GPUと同じ見出しにしない（物理枚数への混入を防ぐ）
    return f"{label} ({UNIT_LABELS[unit]})" if unit in ("mig_instance", "virtual_fraction") else label


def _allocated_for(node: Node, entry: GresEntry, gpu_entries: list[GresEntry]) -> int | None:
    used = _allocated_from_gres_used(node, entry)
    if used is not None:
        return used
    if node.alloc_tres is None:
        return None
    typed_key = f"gres/gpu:{entry.gpu_type}" if entry.gpu_type else None
    if typed_key and typed_key in node.alloc_tres:
        return _to_int(node.alloc_tres[typed_key])
    if len(gpu_entries) == 1:
        # 種類が1つだけなら gres/gpu の合計がその種類の割当数になる
        return _to_int(node.alloc_tres.get("gres/gpu", "0"))
    has_any_gpu = any(k.startswith("gres/gpu") for k in node.alloc_tres)
    return 0 if not has_any_gpu else None


def _allocated_from_gres_used(node: Node, entry: GresEntry) -> int | None:
    for used in parse_gres(node.gres_used_raw):
        if used.name == "gpu" and used.gpu_type == entry.gpu_type:
            return used.count
    return None


def node_gpu_allocations(node: Node) -> list[GpuAllocation]:
    gpu_entries = [e for e in parse_gres(node.gres_raw) if e.name == "gpu"]
    allocations = []
    for entry in gpu_entries:
        allocated = _allocated_for(node, entry, gpu_entries)
        total = entry.count
        free = total - allocated if total is not None and allocated is not None else None
        allocations.append(
            GpuAllocation(
                node_name=node.name,
                gpu_type=entry.gpu_type or "不明",
                resource_unit=classify_unit(entry.gpu_type),
                total=total,
                allocated=allocated,
                free=free if free is None or free >= 0 else None,
                source="scontrol(Gres/AllocTRES)",
                partitions=node.partitions,
                node_state=node.state_raw,
            )
        )
    return allocations


def gpu_allocations(nodes: Iterable[Node]) -> list[GpuAllocation]:
    unique = {n.name: n for n in nodes}
    result: list[GpuAllocation] = []
    for node in unique.values():
        result.extend(node_gpu_allocations(node))
    return result


def _sum_or_none(values: list[int | None]) -> int | None:
    return None if any(v is None for v in values) else sum(v for v in values if v is not None)


def summarize(allocations: Iterable[GpuAllocation]) -> list[GpuGroupSummary]:
    groups: dict[tuple[str, str], list[GpuAllocation]] = {}
    for a in allocations:
        key = (classify_group(a.gpu_type, a.node_name, a.resource_unit), a.resource_unit)
        groups.setdefault(key, []).append(a)
    summaries = []
    for (group, unit), items in sorted(groups.items()):
        total = _sum_or_none([i.total for i in items])
        allocated = _sum_or_none([i.allocated for i in items])
        free = total - allocated if total is not None and allocated is not None else None
        summaries.append(
            GpuGroupSummary(group, unit, total, allocated, free, len({i.node_name for i in items}))
        )
    return summaries


UNIT_LABELS = {
    "physical_gpu": "物理GPU",
    "mig_instance": "MIGインスタンス",
    "virtual_fraction": "仮想/分割GPU",
    "unknown": "単位不明",
}
