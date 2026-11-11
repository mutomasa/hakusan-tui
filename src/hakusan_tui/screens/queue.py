"""キュータブ（全ユーザーの閲覧可能なジョブ、待機理由、パーティション別集計）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Input, Label, Select, Static

from hakusan_tui.formatting import fmt_duration, fmt_time, job_state, job_where
from hakusan_tui.i18n import explain_reason
from hakusan_tui.models import Job
from hakusan_tui.screens.base import BaseTab, matches
from hakusan_tui.widgets.tables import fill_table, selected_key

COLUMNS = ("JOBID", "USER", "PARTITION", "名前", "STATE", "TIME", "TIME_LIMIT",
           "NODELIST(REASON)", "推定開始(Slurm推定)")


def partition_summary(jobs: list[Job]) -> list[tuple[str, tuple[str, ...]]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for j in jobs:
        s = stats[j.partition or "—"]
        s["running"] += j.is_running
        s["pending"] += j.is_pending
        s["resources"] += j.is_pending and j.reason == "Resources"
    rows = []
    for name, s in sorted(stats.items()):
        crowd = "混雑" if s["resources"] else ("待機あり" if s["pending"] else "—")
        rows.append((name, (name, str(s["running"]), str(s["pending"]), str(s["resources"]), crowd)))
    return rows


class QueueTab(BaseTab):
    HELP_TITLE = "キュー"
    HELP_TEXT = (
        "クラスタ全体のジョブのうち、**あなたに公開されている範囲**を表示します。"
        "サイト設定により他ユーザーのジョブが一部しか見えないことがあります。\n\n"
        "- 推定開始は `squeue --start` の **Slurm推定** で、保証されません。\n"
        "- 他ユーザーのジョブは閲覧のみで、操作はできません。"
    )
    COMMANDS = ("squeue", "squeue --start")

    def compose(self) -> ComposeResult:
        yield Static("表示範囲: ユーザーに公開されているジョブのみ", classes="hint")
        yield Label("パーティション別の状況", classes="section-title")
        yield DataTable(id="queue-summary", cursor_type="row")
        with Horizontal(classes="toolbar"):
            yield Select([("すべて", "all"), ("実行中", "running"), ("待機中", "pending")],
                         value="all", allow_blank=False, id="queue-filter", classes="filter")
            yield Input(placeholder="/ ユーザー・パーティション・名前で検索", id="queue-search",
                        classes="search")
        yield DataTable(id="queue-table", cursor_type="row", zebra_stripes=True)
        yield Static(id="queue-reason", classes="hint")

    def _visible(self) -> list[Job]:
        mode = self.query_one("#queue-filter", Select).value
        query = self.query_one("#queue-search", Input).value
        jobs = [j for j in self.ctx.jobs() if j.is_pending or j.is_running
                or j.state_normalized == "COMPLETING"]
        if mode == "running":
            jobs = [j for j in jobs if j.is_running]
        elif mode == "pending":
            jobs = [j for j in jobs if j.is_pending]
        return [j for j in jobs if matches(query, j.user, j.partition, j.name, j.job_id)]

    def update_view(self) -> None:
        active = [j for j in self.ctx.jobs() if j.is_active]
        fill_table(self.query_one("#queue-summary", DataTable),
                   ("パーティション", "実行", "待機", "うち資源待ち", "状況"), partition_summary(active))
        starts = self.ctx.start_estimates()
        rows = [(j.job_id, (j.job_id, j.user, j.partition or "—", j.name, job_state(j),
                            fmt_duration(j.elapsed_seconds), fmt_duration(j.time_limit_seconds),
                            job_where(j), self._start_text(j, starts)))
                for j in self._visible()]
        fill_table(self.query_one("#queue-table", DataTable), COLUMNS, rows)
        self._update_reason()

    @staticmethod
    def _start_text(job: Job, starts: dict[str, object]) -> str:
        when = starts.get(job.job_id) if job.is_pending else None
        return fmt_time(when) if isinstance(when, datetime) else "—"

    def _selected(self) -> Job | None:
        key = selected_key(self.query_one("#queue-table", DataTable))
        return next((j for j in self.ctx.jobs() if j.job_id == key), None)

    def _update_reason(self) -> None:
        job = self._selected()
        text = ""
        if job is not None and job.is_pending:
            text = f"待機理由 {job.reason}: {explain_reason(job.reason)}"
        elif job is not None:
            text = f"{job.user} のジョブ {job.job_id}（{job_state(job)}）[Enter]詳細"
        self.query_one("#queue-reason", Static).update(Text(text))

    def on_select_changed(self, _event: Select.Changed) -> None:
        self.update_view()

    def on_input_changed(self, _event: Input.Changed) -> None:
        self.update_view()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "queue-table":
            self._update_reason()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        job = self._selected() if event.data_table.id == "queue-table" else None
        if job is not None:
            self.happ.open_job_detail(job)
