"""確認ダイアログ・テキスト表示ダイアログ。"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown, Static


class ConfirmScreen(ModalScreen[bool]):
    """実行するコマンドを見せてから明示確認する。既定のフォーカスは「やめる」。"""

    BINDINGS = [Binding("escape", "cancel", "閉じる")]

    def __init__(self, title: str, body: str, command: str, confirm_label: str,
                 danger: bool = True):
        super().__init__()
        self._title = title
        self._body = body
        self._command = command
        self._confirm_label = confirm_label
        self._danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, classes="dialog-title")
            yield Static(Text(self._body), classes="dialog-body")
            yield Label("実行するコマンド:")
            yield Static(Text(self._command), classes="command-preview")
            with Horizontal(classes="dialog-buttons"):
                yield Button("やめる", id="no", variant="primary")
                yield Button(self._confirm_label, id="yes",
                             variant="error" if self._danger else "success")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class TextScreen(ModalScreen[None]):
    """長いテキスト（説明・生出力）を表示する。"""

    BINDINGS = [Binding("escape", "close", "閉じる"), Binding("q", "close", "閉じる", show=False)]

    def __init__(self, title: str, text: str, markdown: bool = False):
        super().__init__()
        self._title = title
        self._text = text
        self._markdown = markdown

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog", classes="wide"):
            yield Label(self._title, classes="dialog-title")
            with VerticalScroll(classes="dialog-scroll"):
                yield Markdown(self._text) if self._markdown else Static(Text(self._text))
            with Horizontal(classes="dialog-buttons"):
                yield Button("閉じる (Esc)", id="close", variant="primary")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
