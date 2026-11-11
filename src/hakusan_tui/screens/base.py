"""タブの基底クラス。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Input

from hakusan_tui.context import AppContext

if TYPE_CHECKING:
    from hakusan_tui.app import HakusanApp


class BaseTab(Vertical):
    HELP_TITLE = ""
    HELP_TEXT = ""
    COMMANDS: tuple[str, ...] = ()

    @property
    def happ(self) -> HakusanApp:
        return cast("HakusanApp", self.app)

    @property
    def ctx(self) -> AppContext:
        return self.happ.ctx

    def update_view(self) -> None:
        """スナップショット更新時に呼ばれる。"""

    def on_mount(self) -> None:
        self.update_view()

    def focus_search(self) -> bool:
        try:
            self.query_one(".search", Input).focus()
        except NoMatches:
            return False
        return True

    def help_markdown(self) -> str:
        commands = "\n".join(f"- `{c}`" for c in self.COMMANDS) or "- なし"
        return f"{self.HELP_TEXT}\n\n**この画面で使うコマンド**\n\n{commands}\n"


def matches(query: str, *fields: str | None) -> bool:
    query = query.strip().lower()
    return not query or any(query in (f or "").lower() for f in fields)
