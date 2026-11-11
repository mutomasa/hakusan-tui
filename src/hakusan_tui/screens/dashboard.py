"""概要タブ。共通キャッシュの値だけを表示し、このタブのためにコマンドを発行しない。"""

from __future__ import annotations

from collections import Counter

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import DataTable, Label, Static

from hakusan_tui.adapters.gpu import UNIT_LABELS, gpu_allocations, summarize
from hakusan_tui.context import HISTORY, JOBS, NODES
from hakusan_tui.formatting import bar, fmt_clock, fmt_duration, fmt_int, job_state, pad
from hakusan_tui.i18n import job_state_label, node_state_label
from hakusan_tui.screens.base import BaseTab
from hakusan_tui.widgets.tables import fill_table

FINISHED = ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL")


class DashboardTab(BaseTab):
    HELP_TITLE = "概要"
    HELP_TEXT = (
        "クラスタ全体と自分のジョブの状況をまとめて表示します。\n\n"
        "- GPUは **Slurm上の割当数** です。実際の使用率ではありません。\n"
        "- 取得できない値は「—」「不明」と表示し、0 とは区別します。"
    )
    COMMANDS = ("squeue", "scontrol show node -o", "sacct")

    def compose(self) -> ComposeResult:
        with Grid(id="cards"):
            yield Static(id="card-my", classes="card")
            yield Static(id="card-cluster", classes="card")
            yield Static(id="card-nodes", classes="card")
            yield Static(id="card-gpu", classes="card")
        yield Static(id="card-source", classes="source-line")
        with Horizontal(classes="split"):
            with Vertical():
                yield Label("自分の待機ジョブ（上位5件）", classes="section-title")
                yield DataTable(id="dash-pending", cursor_type="row")
            with Vertical():
                yield Label("最近終了した自分のジョブ（上位5件）", classes="section-title")
                yield DataTable(id="dash-finished", cursor_type="row")

    def update_view(self) -> None:
        self._update_cards()
        self._update_tables()

    def _update_cards(self) -> None:
        mine = Counter(j.state_normalized for j in self.ctx.my_jobs())
        finished = sum(1 for r in self.ctx.history() if r.state_normalized in FINISHED)
        self.query_one("#card-my", Static).update(Text(
            "自分のジョブ\n"
            f"  実行中 {mine['RUNNING']}   待機中 {mine['PENDING']}\n"
            f"  終了（履歴 {self.ctx.history_days}日） {finished if self.ctx.snapshot(HISTORY).value is not None else '—'}"
        ))
        allj = Counter(j.state_normalized for j in self.ctx.jobs())
        self.query_one("#card-cluster", Static).update(Text(
            "クラスタ全体（閲覧可能な範囲）\n"
            f"  実行中 {allj['RUNNING']}   待機中 {allj['PENDING']}\n"
            f"  完了処理中 {allj['COMPLETING']}"
        ))
        self.query_one("#card-nodes", Static).update(Text(self._nodes_text()))
        self.query_one("#card-gpu", Static).update(Text(self._gpu_text()))
        self.query_one("#card-source", Static).update(Text(self._source_text()))

    def _nodes_text(self) -> str:
        nodes = self.ctx.nodes()
        if not nodes:
            return "ノード\n  情報取得中/取得不可"
        counts = Counter(n.base_state for n in nodes)
        items = [f"{node_state_label(s)} {c}" for s, c in counts.most_common()]
        return "ノード（Slurm状態）\n  " + "  ".join(items[:3]) + ("\n  " + "  ".join(items[3:6]) if len(items) > 3 else "")

    def _gpu_text(self) -> str:
        summaries = summarize(gpu_allocations(self.ctx.nodes()))
        if not summaries:
            return "GPU（Slurm割当ベース）\n  GPUノード情報なし"
        lines = ["GPU（Slurm割当ベース）"]
        for s in summaries:
            unit = "" if s.resource_unit == "physical_gpu" else f" {UNIT_LABELS[s.resource_unit]}"
            lines.append(
                f"  {pad(s.group + unit, 18)} {bar(s.allocated, s.total)} "
                f"{fmt_int(s.allocated)} / {fmt_int(s.total)}"
            )
        return "\n".join(lines)

    def _source_text(self) -> str:
        jobs, nodes = self.ctx.snapshot(JOBS), self.ctx.snapshot(NODES)
        demo = "【デモデータ・実環境の値ではありません】 " if self.ctx.adapter.mode == "demo" else ""
        return (f"{demo}取得元: squeue（{fmt_clock(jobs.last_success)}） / "
                f"scontrol show node（{fmt_clock(nodes.last_success)}） / sacct")

    def _update_tables(self) -> None:
        pending = [j for j in self.ctx.my_jobs() if j.is_pending][:5]
        fill_table(
            self.query_one("#dash-pending", DataTable),
            ("ID", "名前", "区分", "状態", "待機理由"),
            [(j.job_id, (j.job_id, j.name, j.partition or "—", job_state(j), j.reason or "—"))
             for j in pending],
        )
        finished = [r for r in self.ctx.history() if r.state_normalized in FINISHED][:5]
        fill_table(
            self.query_one("#dash-finished", DataTable),
            ("ID", "名前", "状態", "経過", "ExitCode"),
            [(r.job_id, (r.job_id, r.name, job_state_label(r.state_normalized),
                         fmt_duration(r.elapsed_seconds), r.exit_code or "—"))
             for r in finished],
        )
