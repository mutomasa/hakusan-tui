"""ジョブ詳細ダイアログ（基本情報・資源・ログ末尾・操作）。"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from hakusan_tui.context import AppContext
from hakusan_tui.formatting import fmt_duration, fmt_time, job_state
from hakusan_tui.i18n import explain_reason
from hakusan_tui.models import Job
from hakusan_tui.services.jobs import can_cancel


def job_info_table(job: Job) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()
    rows = [
        ("JobID", job.job_id), ("名前", job.name), ("所有者", job.user),
        ("状態", f"{job_state(job)}  [{job.state_raw}]"),
        ("待機理由", f"{job.reason or '—'}  {explain_reason(job.reason) if job.is_pending else ''}"),
        ("パーティション", job.partition or "—"),
        ("投入時刻", fmt_time(job.submit_time)), ("開始時刻", fmt_time(job.start_time)),
        ("経過 / 制限", f"{fmt_duration(job.elapsed_seconds)} / {fmt_duration(job.time_limit_seconds)}"),
        ("ノード", job.node_list or "—"),
        ("ReqTRES", _tres(job.requested_tres)), ("AllocTRES", _tres(job.allocated_tres)),
        ("TresPerNode", job.tres_per_node or "—"),
        ("WorkDir", job.work_dir or "—"), ("StdOut", job.stdout_path or "—"),
        ("StdErr", job.stderr_path or "—"), ("ExitCode", job.exit_code or "—"),
    ]
    for key, value in rows:
        table.add_row(key, Text(value))
    return table


def _tres(tres: dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in tres.items()) or "—"


class JobDetailScreen(ModalScreen[str | None]):
    """閉じるときに ``"cancel"`` を返すとアプリ側でキャンセル確認を開始する。"""

    BINDINGS = [
        Binding("escape", "close", "閉じる"),
        Binding("l", "reload_log", "ログ再読込"),
        Binding("e", "toggle_stream", "stdout/stderr切替"),
    ]

    def __init__(self, ctx: AppContext, job: Job):
        super().__init__()
        self._ctx = ctx
        self._job = job
        self._stream = "stdout"

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="wide"):
            yield Label(f"ジョブ詳細  {self._job.job_id}  {self._job.name}", classes="dialog-title")
            with VerticalScroll(classes="dialog-scroll"):
                yield Static(job_info_table(self._job), id="job-info")
                yield Label("実行中ステップ統計 (sstat)", classes="section-title")
                yield Static("—", id="job-sstat")
                yield Label("ログ末尾（読み取り専用・最大1MiB）", classes="section-title", id="log-title")
                yield Static("読み込み中…", id="job-log", classes="log-view")
            with Horizontal(classes="dialog-buttons"):
                yield Button("ログ再読込 (l)", id="reload")
                yield Button("stdout/stderr (e)", id="toggle")
                yield Button("キャンセル…", id="cancel", variant="error")
                yield Button("閉じる (Esc)", id="close", variant="primary")

    def on_mount(self) -> None:
        ok, reason = can_cancel(self._job, self._ctx.user, self._ctx.read_only)
        button = self.query_one("#cancel", Button)
        button.disabled = not ok
        button.tooltip = reason or "scancel を確認付きで実行"
        self.load_detail()

    @work(exclusive=True, group="detail")
    async def load_detail(self) -> None:
        if self._ctx.adapter.mode != "demo" and self._job.job_id.isdigit():
            detail = await self._ctx.adapter.get_job_detail(self._job.job_id)
            if detail is not None:
                self._job = detail
                self.query_one("#job-info", Static).update(job_info_table(detail))
        if self._job.is_running and self._ctx.caps.sstat:
            result = await self._ctx.adapter.get_sstat(self._job.job_id)
            text = result.stdout.strip() if result.ok else f"取得不可: {result.error_message()}"
            self.query_one("#job-sstat", Static).update(Text(text or "データなし"))
        self._show_log()

    def _show_log(self) -> None:
        if self._job.user != self._ctx.user:
            self.query_one("#job-log", Static).update("他のユーザーのジョブのログは表示しません")
            return
        path = self._job.stdout_path if self._stream == "stdout" else self._job.stderr_path
        view = self._ctx.read_log(path)
        title = f"ログ末尾 [{self._stream}] {view.path}" + ("（先頭を省略）" if view.truncated else "")
        self.query_one("#log-title", Label).update(title)
        body = view.error or view.text or "（空）"
        self.query_one("#job-log", Static).update(Text(body[-20000:]))

    def action_reload_log(self) -> None:
        self._show_log()

    def action_toggle_stream(self) -> None:
        self._stream = "stderr" if self._stream == "stdout" else "stdout"
        self._show_log()

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {"reload": self.action_reload_log, "toggle": self.action_toggle_stream,
                   "close": self.action_close}
        if event.button.id == "cancel":
            self.dismiss("cancel")
        elif event.button.id in actions:
            actions[event.button.id]()

    @property
    def job(self) -> Job:
        return self._job
