"""Textual アプリ本体（9タブ・共通ヘッダー/フッター・更新制御）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, Static, TabbedContent, TabPane, TextArea

from hakusan_tui.adapters.base import ClusterAdapter
from hakusan_tui.config import Config
from hakusan_tui.context import HISTORY, JOBS, NODES, PARTITIONS, SPART, START, AppContext
from hakusan_tui.formatting import fmt_clock, job_state
from hakusan_tui.models import Job
from hakusan_tui.screens.base import BaseTab
from hakusan_tui.screens.dashboard import DashboardTab
from hakusan_tui.screens.gpu import GpuTab
from hakusan_tui.screens.help import HelpTab
from hakusan_tui.screens.history import HistoryTab
from hakusan_tui.screens.my_jobs import MyJobsTab
from hakusan_tui.screens.nodes import NodesTab
from hakusan_tui.screens.queue import QueueTab
from hakusan_tui.screens.submit import SubmitTab
from hakusan_tui.screens.tools import ToolsTab
from hakusan_tui.services import interactive
from hakusan_tui.services.jobs import JobActionService, can_cancel, cancel_preview
from hakusan_tui.widgets.job_detail import JobDetailScreen
from hakusan_tui.widgets.modals import ConfirmScreen, TextScreen

TABS: tuple[tuple[str, str, type[BaseTab]], ...] = (
    ("dashboard", "概要", DashboardTab),
    ("my_jobs", "自分のジョブ", MyJobsTab),
    ("queue", "キュー", QueueTab),
    ("gpu", "GPU", GpuTab),
    ("nodes", "ノード", NodesTab),
    ("submit", "ジョブ投入", SubmitTab),
    ("history", "履歴", HistoryTab),
    ("tools", "ツール", ToolsTab),
    ("help", "ヘルプ", HelpTab),
)
TAB_IDS = tuple(t[0] for t in TABS)
TEXT_INPUTS = (Input, TextArea)


class HakusanApp(App[None]):
    TITLE = "HAKUSAN TUI"
    CSS_PATH = "resources/app.tcss"
    BINDINGS = [
        *(Binding(str(i + 1), f"switch_tab('{tab_id}')", label, show=False)
          for i, (tab_id, label, _cls) in enumerate(TABS)),
        Binding("r", "refresh", "更新"),
        Binding("s", "switch_tab('submit')", "投入"),
        Binding("slash", "search", "検索"),
        Binding("question_mark", "tab_help", "説明"),
        Binding("q", "quit_app", "終了"),
    ]

    def __init__(self, config: Config, adapter: ClusterAdapter):
        super().__init__()
        self.ctx = AppContext(config=config, adapter=adapter,
                              history_days=config.history.default_days)
        self._status = ""

    # ------------------------------------------------------------ 構築

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with TabbedContent(initial=self._initial_tab(), id="main-tabs"):
            for i, (tab_id, label, cls) in enumerate(TABS):
                with TabPane(f"{i + 1} {label}", id=tab_id):
                    yield cls()
        yield Static(id="statusbar")
        yield Footer()

    def _initial_tab(self) -> str:
        tab = self.ctx.config.ui.default_tab
        return tab if tab in TAB_IDS else "dashboard"

    def on_mount(self) -> None:
        self._update_topbar()
        self.startup()

    @work(group="startup")
    async def startup(self) -> None:
        self.ctx.caps = await self.ctx.adapter.detect_capabilities()
        if not self.ctx.caps.slurm_available:
            self._set_status("Slurm に接続できません: " + "; ".join(self.ctx.caps.notes))
        refresh = self.ctx.config.refresh
        await self._refresh_all()
        self.set_interval(refresh.jobs_seconds, lambda: self.refresh_jobs())
        self.set_interval(refresh.nodes_seconds, lambda: self.refresh_nodes())
        self.set_interval(refresh.history_seconds, self._tick_history)

    async def _refresh_all(self) -> None:
        await self._load_jobs(False)
        await self._load_nodes(False)
        await self._load_history(False)

    # ------------------------------------------------------------ 取得

    async def _fetch(self, key: str, loader: Callable[[], Awaitable[Any]], ttl: float,
                     force: bool) -> None:
        snap = await self.ctx.store.fetch(key, loader, ttl, force)
        warnings = self.ctx.adapter.take_warnings()
        if snap.last_error:
            self._set_status(f"{key} の取得に失敗（直前のデータを表示中）: {snap.last_error}")
        elif warnings:
            self._set_status("注意: " + warnings[-1])

    async def _load_jobs(self, force: bool) -> None:
        ttl = self.ctx.config.refresh.jobs_seconds
        await self._fetch(JOBS, self.ctx.adapter.get_jobs, ttl, force)
        await self._fetch(START, self.ctx.adapter.get_start_estimates, ttl * 2, False)
        self._push_updates()

    async def _load_nodes(self, force: bool) -> None:
        ttl = self.ctx.config.refresh.nodes_seconds
        await self._fetch(NODES, self.ctx.adapter.get_nodes, ttl, force)
        await self._fetch(SPART, self.ctx.adapter.get_spart, ttl * 4, force)
        await self._fetch(PARTITIONS, self.ctx.adapter.get_partitions, ttl, force)
        self._push_updates()

    async def _load_history(self, force: bool) -> None:
        if not self.ctx.caps.sacct:
            self.ctx.store.get(HISTORY).last_error = "sacct が見つかりません"
            self._push_updates()
            return
        days, limit = self.ctx.history_days, self.ctx.config.history.max_records
        key = f"{HISTORY}"
        if force:
            self.ctx.store.invalidate(key)
        await self._fetch(key, lambda: self.ctx.adapter.get_history(days, limit),
                          self.ctx.config.refresh.history_seconds, False)
        self._push_updates()

    @work(group="refresh-jobs")
    async def refresh_jobs(self, force: bool = False) -> None:
        await self._load_jobs(force)

    @work(group="refresh-nodes")
    async def refresh_nodes(self, force: bool = False) -> None:
        await self._load_nodes(force)

    @work(group="refresh-history")
    async def refresh_history(self, force: bool = False) -> None:
        await self._load_history(force)

    def _tick_history(self) -> None:
        if self._active_tab() in {"history", "dashboard"}:
            self.refresh_history()

    def _push_updates(self) -> None:
        self._update_topbar()
        for tab in self.query(BaseTab):
            try:
                tab.update_view()
            except Exception as exc:  # 1画面の描画失敗でアプリ全体を落とさない
                self._set_status(f"画面更新エラー ({tab.__class__.__name__}): {exc}")

    # ------------------------------------------------------------ ヘッダー/フッター

    def _update_topbar(self) -> None:
        jobs = self.ctx.snapshot(JOBS)
        if jobs.last_error and jobs.value is None:
            conn = "接続: エラー"
        elif jobs.is_stale:
            conn = "接続: エラー（データが古い）"
        elif jobs.last_success:
            conn = "接続: 正常"
        else:
            conn = "接続: 確認中"
        mode = ["デモ"] if self.ctx.adapter.mode == "demo" else []
        mode += ["読取専用"] if self.ctx.read_only else []
        text = (f" HAKUSAN | {self.ctx.user} | {self.ctx.adapter.hostname} | "
                f"最終更新 {fmt_clock(jobs.last_success)} | {conn}"
                + (f" | {' / '.join(mode)}" if mode else ""))
        self.query_one("#topbar", Static).update(Text(text))
        self._render_status()

    def _set_status(self, message: str) -> None:
        self._status = message
        self._render_status()

    def _render_status(self) -> None:
        refresh = self.ctx.config.refresh
        interval = f"更新間隔: ジョブ{refresh.jobs_seconds:g}s / ノード{refresh.nodes_seconds:g}s"
        self.query_one("#statusbar", Static).update(
            Text(f" {self._status}  |  {interval}" if self._status else f" {interval}")
        )

    # ------------------------------------------------------------ キー操作

    def _active_tab(self) -> str:
        return self.query_one("#main-tabs", TabbedContent).active

    def _active_tab_widget(self) -> BaseTab | None:
        pane = self.query_one("#main-tabs", TabbedContent).active_pane
        return pane.query_one(BaseTab) if pane else None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # 入力欄にフォーカス中は 1〜9 / r / s / q / ? / / を文字入力として扱う
        return not (isinstance(self.focused, TEXT_INPUTS) and action in {"switch_tab", "refresh", "search", "tab_help", "quit_app"})

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one("#main-tabs", TabbedContent).active = tab_id
        if tab_id == "history":
            self.refresh_history()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id == "main-tabs" and event.pane.id == "history":
            self.refresh_history()

    def action_refresh(self) -> None:
        tab = self._active_tab()
        if tab in {"nodes", "gpu"}:
            self.refresh_nodes(force=True)
        elif tab == "history":
            self.refresh_history(force=True)
        else:
            self.refresh_jobs(force=True)
        self.notify("更新を要求しました（短いクールダウンがあります）", timeout=2)

    def action_search(self) -> None:
        tab = self._active_tab_widget()
        if tab is None or not tab.focus_search():
            self.notify("この画面には検索欄がありません", timeout=2)

    def action_tab_help(self) -> None:
        tab = self._active_tab_widget()
        if tab is not None:
            self.push_screen(TextScreen(f"この画面の説明: {tab.HELP_TITLE}", tab.help_markdown(),
                                        markdown=True))

    def action_quit_app(self) -> None:
        submit = self.query_one(SubmitTab)
        if not submit.dirty:
            self.exit()
            return
        self.push_screen(
            ConfirmScreen("終了の確認", "ジョブ投入フォームに保存していない変更があります。",
                          "hakusan-tui を終了（実行中のバッチジョブは止まりません）", "終了する"),
            lambda ok: self.exit() if ok else None,
        )

    # ------------------------------------------------------------ 画面間の操作

    def open_job_detail(self, job: Job) -> None:
        self.push_screen(JobDetailScreen(self.ctx, job),
                         lambda result: self.request_cancel(job) if result == "cancel" else None)

    def request_cancel(self, job: Job) -> None:
        ok, reason = can_cancel(job, self.ctx.user, self.ctx.read_only)
        if not ok:
            self.notify(reason, severity="warning")
            return
        body = (f"ジョブID: {job.job_id}\n名前: {job.name}\n状態: {job_state(job)}\n"
                f"所有者: {job.user}\n\n実行直前にも所有者と状態を再確認します。")
        self.push_screen(
            ConfirmScreen("ジョブのキャンセル", body, cancel_preview(job.job_id), "はい、キャンセル"),
            lambda confirmed: self._do_cancel(job.job_id) if confirmed else None,
        )

    @work(group="cancel")
    async def _do_cancel(self, job_id: str) -> None:
        outcome = await JobActionService(self.ctx.adapter, self.ctx.read_only).cancel(job_id)
        self.notify(outcome.message, severity="information" if outcome.ok else "error", timeout=8)
        if outcome.executed:
            await self._load_jobs(force=True)  # 成功確認後に一覧を再取得（先に消さない）

    def use_partition(self, name: str) -> None:
        self.query_one(SubmitTab).set_partition(name)
        self.action_switch_tab("submit")

    def add_modules_to_submit(self, names: list[str]) -> None:
        self.query_one(SubmitTab).add_modules(names)
        self.notify(f"投入フォームに追加: {', '.join(names)}")

    def open_submit_template(self, key: str) -> None:
        self.query_one(SubmitTab).set_template(key)
        self.action_switch_tab("submit")

    def run_interactive(self, argv: list[str]) -> None:
        if not self.ctx.writable:
            self.notify("読み取り専用/デモモードのため実行しません", severity="warning")
            return
        with self.suspend():
            code = interactive.run_interactive(argv)
        self.notify(f"対話ジョブから戻りました（終了コード {code}）")
        self.refresh_jobs(force=True)
