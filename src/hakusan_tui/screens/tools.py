"""ツールタブ（Module / 対話ジョブ / ステージング / PBS互換 / 環境診断）。"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Markdown,
    SelectionList,
    Static,
    TabbedContent,
    TabPane,
)

from hakusan_tui.adapters.tools import parse_module_terse
from hakusan_tui.screens.base import BaseTab
from hakusan_tui.services import interactive
from hakusan_tui.services.diagnostics import diagnose
from hakusan_tui.widgets.modals import ConfirmScreen, TextScreen
from hakusan_tui.widgets.tables import fill_table

MODULE_NOTE = (
    "`module load` はシェル関数で、TUI のサブプロセスで実行しても **今のログインシェルには引き継がれません**。"
    "ここで選んだモジュールは「投入フォームに追加」で **これから生成するジョブスクリプト** に書き込みます"
    "（資料 p.27–30）。コンパイルもジョブとして計算ノードで行ってください（p.19）。"
)

STAGING_MD = """\
### /home と $JOBDIR（資料 p.8, 22, 50–52）

| 領域 | 用途 | 注意 |
|---|---|---|
| `/home` | スクリプト・ソース・成果物の保存 | 共有領域 |
| `/JOBs` / `$JOBDIR` | ジョブ実行中の高速作業領域 | **ジョブ終了で削除** |

**流れ**: input を `$SLURM_SUBMIT_DIR` → `$JOBDIR` へコピー → `$JOBDIR` で計算 →
output を `$SLURM_SUBMIT_DIR` へ戻す（copy-back）。

- テンプレートは `trap ... EXIT` で、計算が失敗しても copy-back を試みます。
- コピーの失敗は標準エラーに記録されます。必要容量と転送時間に注意してください。
- 計算中の `$JOBDIR` を TUI から消す機能はありません。
"""

PBS_MD = """\
### PBS互換コマンド（上級者向け・資料 p.56）

HAKUSAN は Slurm 上で PBS 互換ラッパーを提供しています。**すべての PBS オプションには対応していません。**
TUI の主経路は Slurm で、PBS 互換は参照と案内のみです。

| PBS | Slurm 相当 | TUIでの扱い |
|---|---|---|
| `qsub job.sh` | `sbatch job.sh` | 投入タブを使用 |
| `qstat` | `squeue` | 下のボタンで読み取り表示 |
| `qdel <ID>` | `scancel <ID>` | 自分のジョブタブのキャンセル（所有者確認+二段階確認） |
| `qalter` / `qhold` / `qrls` / `qrerun` | `scontrol update/hold/release/requeue` | 未対応（シェルで実行） |
| `pbsnodes` | `sinfo -N` / `scontrol show node` | 下のボタンで読み取り表示 |
| `mpiexec` / `generate_pbs_nodefile` | — | **ジョブスクリプト内でのみ** 使用 |
"""


class ToolsTab(BaseTab):
    HELP_TITLE = "ツール"
    HELP_TEXT = "Module、対話ジョブ（salloc）、ステージング、PBS互換、環境診断をまとめています。"
    COMMANDS = ("module -t avail", "module -t list", "module show <name>", "salloc ...",
                "qstat", "pbsnodes -a")

    def compose(self) -> ComposeResult:
        with TabbedContent(id="tools-tabs"):
            with TabPane("Module", id="tools-module"):
                yield Static(Text.from_markup(MODULE_NOTE.replace("`", "")), classes="hint")
                with Horizontal(classes="toolbar"):
                    yield Button("module avail", id="mod-avail", variant="primary")
                    yield Button("module list", id="mod-list")
                    yield Button("module show", id="mod-show")
                    yield Button("コンパイラ診断", id="mod-which")
                    yield Button("投入フォームに追加", id="mod-add", variant="success")
                yield SelectionList[str](id="mod-selection")
            with TabPane("対話ジョブ", id="tools-interactive"):
                yield from self._compose_interactive()
            with TabPane("ステージング", id="tools-staging"), VerticalScroll():
                yield Markdown(STAGING_MD)
                yield Button("ステージング付きテンプレートで投入フォームを開く",
                             id="staging-template", variant="primary")
            with TabPane("PBS互換", id="tools-pbs"), VerticalScroll():
                yield Static(id="pbs-detect", classes="hint")
                yield Markdown(PBS_MD)
                with Horizontal(classes="toolbar"):
                    yield Button("qstat", id="pbs-qstat")
                    yield Button("pbsnodes -a", id="pbs-nodes")
            with TabPane("環境診断", id="tools-diag"):
                yield Button("診断を実行", id="diag-run", variant="primary")
                yield DataTable(id="diag-table", cursor_type="row")

    def _compose_interactive(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(
                "salloc で対話ジョブを開始します（資料 p.34, 43）。端末は一時的に対話セッションへ"
                "切り替わり、シェルで `exit` すると割当が解放されて TUI に戻ります。\n"
                "参考: GPU系の対話ジョブ上限は資料では12時間、CPU系は48時間（最新のサイト規則を確認）。",
                classes="hint",
            )
            for name, label, value in (
                ("partition", "パーティション (-p)", ""), ("ntasks", "タスク数 (-n)", "1"),
                ("cpus_per_task", "CPU/タスク", ""), ("mem", "メモリ (--mem)", ""),
                ("gpus", "GPU数", ""), ("time", "時間 (--time)", "01:00:00"),
            ):
                yield Label(label)
                yield Input(value=value, id=f"ia-{name}")
            yield Static(id="ia-preview", classes="command-preview")
            yield Button("対話ジョブを開始…", id="ia-start", variant="warning")

    # ------------------------------------------------------------ 共通

    def on_mount(self) -> None:
        self.update_view()
        self._update_interactive_preview()

    def update_view(self) -> None:
        caps = self.ctx.caps
        self.query_one("#pbs-detect", Static).update(
            Text("検出したラッパー: " + (", ".join(caps.pbs_wrappers) or "なし（PBS互換操作は無効）"))
        )
        self.query_one("#pbs-qstat", Button).disabled = "qstat" not in caps.pbs_wrappers
        self.query_one("#pbs-nodes", Button).disabled = "pbsnodes" not in caps.pbs_wrappers
        self.query_one("#ia-start", Button).disabled = not self.ctx.writable

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "mod-avail": self._module_avail, "mod-list": lambda: self._show_tool("module_list"),
            "mod-show": self._module_show, "mod-which": self._module_which,
            "mod-add": self._module_add, "staging-template": self._staging_template,
            "pbs-qstat": lambda: self._show_tool("qstat"),
            "pbs-nodes": lambda: self._show_tool("pbsnodes"),
            "diag-run": self._diagnose, "ia-start": self._confirm_interactive,
        }
        handler = handlers.get(event.button.id or "")
        if handler:
            handler()

    @work(group="tools")
    async def _show_tool(self, name: str, args: tuple[str, ...] = ()) -> None:
        try:
            result = await self.ctx.adapter.run_readonly_tool(name, args)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return
        body = result.stdout if result.ok else result.error_message()
        self.app.push_screen(TextScreen(" ".join(result.argv[:4]), body or "（出力なし）"))

    # ------------------------------------------------------------ Module

    @work(group="tools")
    async def _module_avail(self) -> None:
        result = await self.ctx.adapter.run_readonly_tool("module_avail")
        if not result.ok:
            self.app.notify(f"module avail 失敗: {result.error_message()}", severity="error")
            return
        selection = self.query_one("#mod-selection", SelectionList)
        selection.clear_options()
        selection.add_options([(name, name) for name in parse_module_terse(result.stdout)])

    def _selected_modules(self) -> list[str]:
        return list(self.query_one("#mod-selection", SelectionList).selected)

    def _module_show(self) -> None:
        selected = self._selected_modules()
        if len(selected) != 1:
            self.app.notify("module show は1つだけ選択してください", severity="warning")
            return
        self._show_tool("module_show", (selected[0],))

    def _module_which(self) -> None:
        self._show_tool("module_which", tuple(self._selected_modules()))

    def _module_add(self) -> None:
        selected = self._selected_modules()
        if not selected:
            self.app.notify("追加するモジュールを選択してください", severity="warning")
            return
        self.happ.add_modules_to_submit(selected)

    def _staging_template(self) -> None:
        self.happ.open_submit_template("staging")

    # ------------------------------------------------------------ 対話ジョブ

    def _interactive_request(self) -> interactive.InteractiveRequest:
        values = {name: self.query_one(f"#ia-{name}", Input).value.strip()
                  for name in ("partition", "ntasks", "cpus_per_task", "mem", "gpus", "time")}
        return interactive.InteractiveRequest(**values)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("ia-"):
            self._update_interactive_preview()

    def _update_interactive_preview(self) -> None:
        try:
            text = interactive.preview(interactive.build_salloc_argv(self._interactive_request()))
        except ValueError as exc:
            text = f"入力エラー: {exc}"
        self.query_one("#ia-preview", Static).update(Text(text))

    def _confirm_interactive(self) -> None:
        try:
            argv = interactive.build_salloc_argv(self._interactive_request())
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.app.push_screen(
            ConfirmScreen("対話ジョブの開始", "端末を対話セッションに切り替えます。\n"
                          "終了はシェルで exit（割当が解放されます）。",
                          interactive.preview(argv), "開始する", danger=False),
            lambda ok: self.happ.run_interactive(argv) if ok else None,
        )

    # ------------------------------------------------------------ 診断

    def _diagnose(self) -> None:
        items = diagnose(self.ctx.adapter, self.ctx.caps)
        fill_table(self.query_one("#diag-table", DataTable), ("結果", "項目", "詳細"),
                   [(str(i), (it.status, it.name, it.detail)) for i, it in enumerate(items)])
