"""DataTable の更新ヘルパー（再描画しても選択行を保持する）。"""

from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey

Row = tuple[str, Sequence[object]]


def ensure_columns(table: DataTable, columns: Sequence[str]) -> None:
    if not table.columns:
        for label in columns:
            table.add_column(label, key=label)


def _safe_cell(value: object) -> object:
    # ジョブ名などに含まれる [ ] を Rich マークアップとして解釈させない
    return Text(value) if isinstance(value, str) else value


def fill_table(table: DataTable, columns: Sequence[str], rows: Sequence[Row]) -> None:
    ensure_columns(table, columns)
    selected = selected_key(table)
    table.clear()
    for key, cells in rows:
        table.add_row(*(_safe_cell(c) for c in cells), key=key)
    if selected is not None and selected in {k for k, _ in rows}:
        table.move_cursor(row=table.get_row_index(selected))


def selected_key(table: DataTable) -> str | None:
    if table.row_count == 0:
        return None
    try:
        row_key: RowKey = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
    except Exception:
        return None
    return row_key.value
