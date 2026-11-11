"""自分のジョブタブ。"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Input, Select, Static

from hakusan_tui.formatting import fmt_duration, fmt_int, job_gpus, job_mem, job_state, job_where
from hakusan_tui.i18n import explain_reason
from hakusan_tui.models import Job
from hakusan_tui.screens.base import BaseTab, matches
from hakusan_tui.widgets.tables import fill_table, selected_key

COLUMNS = ("JOBID", "名前", "パーティション", "状態", "経過", "制限", "CPU", "GPU", "メモリ",
           "ノード数", "割当ノード/(待機理由)")

FILTERS = {
    "all": ("すべて", lambda j: True),
    "running": ("実行中", lambda j: j.state_normalized == "RUNNING"),
    "pending": ("待機中", lambda j: j.state_normalized == "PENDING"),
    "completing": ("完了処理中", lambda j: j.state_normalized == "COMPLETING"),
    "held": ("保留・停止", lambda j: j.state_normalized == "SUSPENDED"
             or (j.reason or "").startswith("JobHeld")),
}


def job_row(job: Job) -> tuple[str, tuple[str, ...]]:
    return job.job_id, (
        job.job_id, job.name, job.partition or "—", job_state(job),
        fmt_duration(job.elapsed_seconds), fmt_duration(job.time_limit_seconds),
        fmt_int(job.n_cpus), job_gpus(job), job_mem(job), fmt_int(job.n_nodes), job_where(job),
    )


class MyJobsTab(BaseTab):
    HELP_TITLE = "自分のジョブ"
    HELP_TEXT = (
        "自分が投入したジョブの一覧です（squeue --me 相当）。\n\n"
        "- `Enter`: 詳細・ログ表示\n- `c`: 選択中のジョブをキャンセル（確認あり）\n"
        "- `/`: 検索\n\n「PD」は待機中、「R」は実行中です。待機中は割当ノードの代わりに（待機理由）を表示します。"
    )
    COMMANDS = ("squeue --me", "scontrol show job <JOBID>", "sstat -j <JOBID>", "scancel <JOBID>")
    BINDINGS = [Binding("c", "cancel_selected", "キャンセル")]

    def compose(self) -> ComposeResult:
        with Horizontal(classes="toolbar"):
            yield Select([(label, key) for key, (label, _) in FILTERS.items()], value="all",
                         allow_blank=False, id="myjobs-filter", classes="filter")
            yield Input(placeholder="/ ジョブID・名前・パーティションで検索", id="myjobs-search",
                        classes="search")
        yield DataTable(id="myjobs-table", cursor_type="row", zebra_stripes=True)
        yield Static(id="myjobs-hint", classes="hint")

    def _visible_jobs(self) -> list[Job]:
        key = self.query_one("#myjobs-filter", Select).value
        predicate = FILTERS.get(str(key), FILTERS["all"])[1]
        query = self.query_one("#myjobs-search", Input).value
        return [j for j in self.ctx.my_jobs()
                if predicate(j) and matches(query, j.job_id, j.name, j.partition)]

    def update_view(self) -> None:
        jobs = self._visible_jobs()
        fill_table(self.query_one("#myjobs-table", DataTable), COLUMNS, [job_row(j) for j in jobs])
        self._update_hint()

    def selected_job(self) -> Job | None:
        key = selected_key(self.query_one("#myjobs-table", DataTable))
        return next((j for j in self.ctx.my_jobs() if j.job_id == key), None)

    def _update_hint(self) -> None:
        job = self.selected_job()
        if job is None:
            text = "ジョブがありません。[s] でジョブ投入タブへ。" if not self.ctx.my_jobs() else ""
        elif job.is_pending:
            text = f"{job.job_id} 待機理由 {job.reason}: {explain_reason(job.reason)}"
        else:
            text = f"{job.job_id} {job_state(job)}  ノード {job.node_list or '—'}  [Enter]詳細 [c]キャンセル"
        self.query_one("#myjobs-hint", Static).update(Text(text))

    def on_select_changed(self, _event: Select.Changed) -> None:
        self.update_view()

    def on_input_changed(self, _event: Input.Changed) -> None:
        self.update_view()

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        self._update_hint()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        job = self.selected_job()
        if job is not None:
            self.happ.open_job_detail(job)

    def action_cancel_selected(self) -> None:
        job = self.selected_job()
        if job is None:
            self.app.notify("キャンセルするジョブを選択してください", severity="warning")
            return
        self.happ.request_cancel(job)
