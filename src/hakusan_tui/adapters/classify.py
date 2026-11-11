"""パーティション・ノードの種別（CPU / GPU / VM）判定。サイトに依存しない。

名前ではなく Slurm 上の構成（GRES・TRES）を根拠にする。構成から判断できないときだけ
名前（``GPU``で始まる / ``VM`` を含む）を手がかりにする。
"""

from __future__ import annotations

from collections.abc import Iterable

from hakusan_tui.adapters.gpu import classify_unit, parse_gres
from hakusan_tui.models import Node, Partition


def _gpu_types(node: Node) -> list[str | None]:
    return [e.gpu_type for e in parse_gres(node.gres_raw)
            if e.name == "gpu" and (e.count is None or e.count > 0)]


def node_has_gpu(node: Node) -> bool:
    return bool(_gpu_types(node))


def node_has_virtual_gpu(node: Node) -> bool:
    return any(classify_unit(t) == "virtual_fraction" for t in _gpu_types(node))


def partition_nodes(part: Partition, nodes: Iterable[Node]) -> list[Node]:
    members = set(part.node_names)
    return [n for n in nodes if n.name in members or part.name in n.partitions]


def _tres_has_gpu(part: Partition) -> bool:
    return any(k == "gres/gpu" or k.startswith("gres/gpu:") for k in part.tres)


def partition_kind(part: Partition, nodes: Iterable[Node] = ()) -> str:
    members = partition_nodes(part, nodes)
    if "VM" in part.name.upper() or any(node_has_virtual_gpu(n) for n in members):
        return "VM"
    if _tres_has_gpu(part) or any(node_has_gpu(n) for n in members):
        return "GPU"
    return "GPU" if part.name.upper().startswith("GPU") else "CPU"


def node_kind(node: Node) -> str:
    if node_has_virtual_gpu(node) or any("VM" in p.upper() for p in node.partitions):
        return "VM"
    if node_has_gpu(node):
        return "GPU"
    if node.partitions or node.cpus_total:
        return "CPU"
    return "不明"
