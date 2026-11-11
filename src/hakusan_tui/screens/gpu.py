"""GPUタブ。A: Slurm割当情報 / B: 実機メトリクス（取得可能時のみ）を明確に分ける。"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Label, Static

from hakusan_tui.adapters.gpu import UNIT_LABELS, gpu_allocations, summarize
from hakusan_tui.adapters.slurm_parsers import expand_hostlist
from hakusan_tui.formatting import bar, fmt_int
from hakusan_tui.i18n import node_state_label
from hakusan_tui.models import GpuAllocation, Job
from hakusan_tui.screens.base import BaseTab
from hakusan_tui.widgets.tables import fill_table

METRICS_NOTICE = (
    "B. 実機メトリクス（利用率・VRAM・温度）: 取得不可 — 自動収集はOFFです。\n"
    "   Slurm accounting の gres/gpuutil・gres/gpumem はサイト設定に依存し、MIG では収集できない"
    "ことがあります。ログインノードから nvidia-smi を連続実行することはしません。"
    "（未取得の値を 0% とは表示しません）"
)


def jobs_by_node(jobs: list[Job]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for job in jobs:
        if not job.is_running or not job.node_list:
            continue
        for node in expand_hostlist(job.node_list):
            mapping.setdefault(node, []).append(job.job_id)
    return mapping


def allocation_row(a: GpuAllocation, jobs: dict[str, list[str]]) -> tuple[str, tuple[str, ...]]:
    base = a.node_state.split("+")[0].rstrip("*~#!%$@^-")
    return f"{a.node_name}:{a.gpu_type}", (
        a.node_name, ",".join(a.partitions) or "—", node_state_label(base), a.gpu_type,
        UNIT_LABELS.get(a.resource_unit, a.resource_unit), fmt_int(a.total), fmt_int(a.allocated),
        fmt_int(a.free), ",".join(jobs.get(a.node_name, [])) or "—",
    )


class GpuTab(BaseTab):
    HELP_TITLE = "GPU"
    HELP_TEXT = (
        "**A. Slurm割当情報**: GRES / AllocTRES から計算した割当数です。\n"
        "「未割当」はSlurm上の未割当で、必ず投入できるという意味ではありません。\n\n"
        "- 複数パーティションに属するノードも1回だけ数えます。\n"
        "- H100の分割GPU/MIGは物理GPU枚数に加算せず、別単位で表示します。\n\n"
        "**B. 実機メトリクス** は取得できる場合のみ表示します。"
    )
    COMMANDS = ("scontrol show node -o", "squeue")

    def compose(self) -> ComposeResult:
        yield Label("A. GPU型別の割当状況（Slurm割当ベース）", classes="section-title")
        yield DataTable(id="gpu-summary", cursor_type="row")
        yield Label("GPUノード一覧", classes="section-title")
        yield DataTable(id="gpu-nodes", cursor_type="row", zebra_stripes=True)
        yield Static(Text(METRICS_NOTICE), id="gpu-metrics", classes="hint")

    def update_view(self) -> None:
        allocations = gpu_allocations(self.ctx.nodes())
        summary_rows = [
            (f"{s.group}:{s.resource_unit}", (
                s.group, UNIT_LABELS.get(s.resource_unit, s.resource_unit), fmt_int(s.total),
                fmt_int(s.allocated), fmt_int(s.free), str(s.node_count), bar(s.allocated, s.total),
            ))
            for s in summarize(allocations)
        ]
        fill_table(self.query_one("#gpu-summary", DataTable),
                   ("グループ", "資源単位", "総数", "割当", "未割当", "ノード数", "割当率"), summary_rows)
        by_node = jobs_by_node(self.ctx.jobs())
        fill_table(self.query_one("#gpu-nodes", DataTable),
                   ("ノード", "パーティション", "状態", "GPU型", "単位", "総数", "割当", "未割当",
                    "割当ジョブ"),
                   [allocation_row(a, by_node) for a in allocations])
