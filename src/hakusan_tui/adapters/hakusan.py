"""HAKUSAN サイトプロファイル（spart 解析、パーティション分類）。

spart の実際の書式は要実機確認。列数が揃った表として読めない場合は原文表示にする。
"""

from __future__ import annotations

from hakusan_tui.models import Node, Partition, SpartTable

LOGIN_HOSTS = ("hakusan1", "hakusan2")


def parse_spart(text: str) -> SpartTable:
    lines = [ln for ln in text.splitlines() if ln.strip() and not set(ln.strip()) <= set("-=")]
    if len(lines) < 3:
        return SpartTable(raw=text)
    top, bottom = lines[0].split(), lines[1].split()
    if len(top) != len(bottom):
        return SpartTable(raw=text)
    headers = tuple(f"{a} {b}" for a, b in zip(top, bottom, strict=True))
    rows = []
    for line in lines[2:]:
        cells = line.split()
        if len(cells) != len(headers):
            return SpartTable(raw=text)
        rows.append(dict(zip(headers, cells, strict=True)))
    return SpartTable(raw=text, headers=headers, rows=tuple(rows), parsed=True)


def spart_partition_name(row: dict[str, str]) -> str:
    """spart の先頭列（``DEF*`` など、* はデフォルト印）からパーティション名。"""
    first = next(iter(row.values()), "")
    return first.rstrip("*")


def merge_spart_limits(partitions: list[Partition], table: SpartTable | None) -> list[Partition]:
    """spart の値を ``site_limits`` に付与する（spart を現行サイト制限として優先表示）。"""
    if table is None or not table.parsed:
        return partitions
    by_name = {spart_partition_name(r): r for r in table.rows}
    merged = []
    for p in partitions:
        row = by_name.get(p.name)
        if row is None:
            merged.append(p)
            continue
        limits = {k: v for k, v in list(row.items())[1:]}
        merged.append(_with_limits(p, limits))
    return merged


def _with_limits(p: Partition, limits: dict[str, str]) -> Partition:
    from dataclasses import replace

    return replace(p, site_limits=limits)


def partition_kind(name: str) -> str:
    upper = name.upper()
    if "VM" in upper:
        return "VM"
    if upper.startswith("GPU"):
        return "GPU"
    return "CPU"


def node_kind(node: Node) -> str:
    if any("VM" in p.upper() for p in node.partitions):
        return "VM"
    if node.gres_raw and "gpu" in node.gres_raw:
        return "GPU"
    if node.partitions or node.cpus_total:
        return "CPU"
    return "不明"
