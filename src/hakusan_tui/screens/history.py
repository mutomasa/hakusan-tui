"""履歴タブ（sacct）。ジョブ行とステップ行（.batch / .0 など）を階層表示する。"""

from __future__ import annotations

import os
import shlex

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Select, Static

from hakusan_tui.context import HISTORY
from hakusan_tui.formatting import fmt_duration, fmt_int, fmt_mib, fmt_time, pad
from hakusan_tui.i18n import job_state_label
from hakusan_tui.models import HistoryRecord, JobStep
from hakusan_tui.screens.base import BaseTab, matches
from hakusan_tui.widgets.modals import TextScreen
from hakusan_tui.widgets.tables import fill_table, selected_key

COLUMNS = ("JOBID", "名前", "State", "ExitCode", "Partition", "Elapsed", "AllocCPUS",
           "AllocTRES", "MaxRSS", "開始", "終了")
MAX_LOG_CANDIDATES = 20


def _tres(tres: dict[str, str]) -> str:
    return ",".join(f"{k}={v}" for k, v in tres.items() if k != "billing") or "—"


def record_rows(r: HistoryRecord) -> list[tuple[str, tuple[str, ...]]]:
    rows = [(r.job_id, (
        r.job_id, r.name, job_state_label(r.state_normalized), r.exit_code or "—",
        r.partition or "—", fmt_duration(r.elapsed_seconds), fmt_int(r.alloc_cpus),
        _tres(r.alloc_tres), fmt_mib(r.max_rss_mib), fmt_time(r.start_time), fmt_time(r.end_time),
    ))]
    rows += [_step_row(s) for s in r.steps]
    return rows


def _step_row(s: JobStep) -> tuple[str, tuple[str, ...]]:
    return s.step_id, (
        f"  └ {s.step_id}", s.name, job_state_label(s.state_normalized), s.exit_code or "—", "",
        fmt_duration(s.elapsed_seconds), fmt_int(s.alloc_cpus), _tres(s.alloc_tres),
        fmt_mib(s.max_rss_mib), "", "",
    )


def compare_text(r: HistoryRecord) -> str:
    lines = [f"{r.job_id} {r.name}  要求と実績（取得できる範囲）"]
    for key in ("cpu", "mem", "gres/gpu", "node"):
        lines.append(f"  {pad(key, 10)} 要求 {r.req_tres.get(key, '—'):<8} 割当 "
                     f"{r.alloc_tres.get(key, '—'):<8}")
    lines.append(f"  MaxRSS(最大実使用メモリ) {fmt_mib(r.max_rss_mib)}"
                 "  ※終了直後はaccounting反映待ちで未確定のことがあります")
    if r.work_dir:
        lines.append(f"  再投入の例（自動実行しません）: cd {shlex.quote(r.work_dir)} && sbatch job.sh")
    return "\n".join(lines)


def find_log_candidates(r: HistoryRecord) -> list[str]:
    """WorkDir 直下でジョブIDを名前に含むファイルを探す（推測でパスを作らない）。"""
    if not r.work_dir or not os.path.isdir(r.work_dir):
        return []
    try:
        names = sorted(n for n in os.listdir(r.work_dir) if r.job_id in n)
    except OSError:
        return []
    return [os.path.join(r.work_dir, n) for n in names[:MAX_LOG_CANDIDATES]]


class HistoryTab(BaseTab):
    HELP_TITLE = "履歴"
    HELP_TEXT = (
        "`sacct` で自分の過去のジョブを表示します（資料 p.46）。\n\n"
        "- `.batch` や `.0` は **ステップ** です。MaxRSS はステップ行に出ることが多く、"
        "ジョブ行にはステップの最大値を表示します。\n"
        "- 終了直後は accounting の反映待ちで値が「未確定」のことがあります。\n"
        "- 期間を限定して取得します（全履歴を無制限に取得しません）。"
    )
    COMMANDS = ("sacct -n -P -S now-7days -u $USER --format=...",)

    def compose(self) -> ComposeResult:
        with Horizontal(classes="toolbar"):
            yield Select([("過去24時間", 1), ("過去7日", 7), ("過去30日", 30)], value=7,
                         allow_blank=False, id="history-days", classes="filter")
            yield Input(placeholder="/ ジョブID・名前・状態で検索", id="history-search",
                        classes="search")
            yield Button("ログを探す", id="history-log")
        yield Static(id="history-status", classes="hint")
        yield DataTable(id="history-table", cursor_type="row", zebra_stripes=True)
        yield Static(id="history-compare", classes="hint")

    def update_view(self) -> None:
        snap = self.ctx.snapshot(HISTORY)
        status = self.query_one("#history-status", Static)
        if snap.last_error and snap.value is None:
            status.update(Text(f"sacct を利用できません: {snap.last_error}（他の機能は利用できます）"))
        elif snap.value is None:
            status.update("読み込み中…（タブ表示時に取得します）")
        else:
            status.update(Text(f"{len(snap.value)} 件（過去{self.ctx.history_days}日・最大"
                               f"{self.ctx.config.history.max_records}件）"))
        query = self.query_one("#history-search", Input).value
        rows = [row for r in self.ctx.history() if matches(query, r.job_id, r.name, r.state_raw)
                for row in record_rows(r)]
        fill_table(self.query_one("#history-table", DataTable), COLUMNS, rows)
        self._update_compare()

    def _selected(self) -> HistoryRecord | None:
        key = selected_key(self.query_one("#history-table", DataTable)) or ""
        job_id = key.split(".", 1)[0]
        return next((r for r in self.ctx.history() if r.job_id == job_id), None)

    def _update_compare(self) -> None:
        record = self._selected()
        self.query_one("#history-compare", Static).update(
            Text(compare_text(record)) if record else ""
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "history-days" and isinstance(event.value, int):
            self.ctx.history_days = event.value
            self.happ.refresh_history(force=True)

    def on_input_changed(self, _event: Input.Changed) -> None:
        self.update_view()

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        self._update_compare()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self._show_log()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "history-log":
            self._show_log()

    def _show_log(self) -> None:
        record = self._selected()
        if record is None:
            return
        if self.ctx.adapter.mode == "demo":
            view = self.ctx.read_log(None)
            self.app.push_screen(TextScreen(f"ログ {record.job_id}（デモ）", view.text))
            return
        candidates = find_log_candidates(record)
        if not candidates:
            self.app.push_screen(TextScreen("ログ", f"WorkDir ({record.work_dir}) にジョブID "
                                            f"{record.job_id} を含むファイルが見つかりません"))
            return
        texts = []
        for path in candidates[:2]:
            view = self.ctx.read_log(path)
            texts.append(f"===== {path} =====\n{view.error or view.text[-20000:]}")
        self.app.push_screen(TextScreen(f"ログ {record.job_id}", "\n".join(texts)))
