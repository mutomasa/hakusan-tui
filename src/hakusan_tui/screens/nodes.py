"""ノードタブ（ノード一覧 / パーティション一覧 / 制限比較(spart)）。"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent, TabPane

from hakusan_tui.adapters.classify import node_kind, partition_kind
from hakusan_tui.formatting import fmt_duration, fmt_int
from hakusan_tui.i18n import node_state_label
from hakusan_tui.models import Node, Partition
from hakusan_tui.screens.base import BaseTab, matches
from hakusan_tui.widgets.modals import TextScreen
from hakusan_tui.widgets.tables import fill_table, selected_key

NODE_COLUMNS = ("ノード", "種別", "状態", "CPU 割当/総数", "メモリ(MiB) 割当/総数", "GRES",
                "パーティション", "理由")
PART_COLUMNS = ("パーティション", "種別", "既定", "状態", "最大時間", "ノード数", "CPU", "TRES")


def node_row(n: Node) -> tuple[str, tuple[str, ...]]:
    return n.name, (
        n.name, node_kind(n), f"{node_state_label(n.base_state)} [{n.state_raw}]",
        f"{fmt_int(n.cpus_allocated)}/{fmt_int(n.cpus_total)}",
        f"{fmt_int(n.memory_allocated_mib)}/{fmt_int(n.memory_total_mib)}",
        n.gres_raw or "—", ",".join(n.partitions) or "—", n.reason or "",
    )


def partition_row(p: Partition, nodes: list[Node] = ()) -> tuple[str, tuple[str, ...]]:
    return p.name, (
        p.name, partition_kind(p, nodes), "○" if p.is_default else "",
        p.state_summary or "不明", fmt_duration(p.max_time_seconds), fmt_int(p.total_nodes),
        fmt_int(p.total_cpus), ",".join(f"{k}={v}" for k, v in p.tres.items()) or "—",
    )


class NodesTab(BaseTab):
    HELP_TITLE = "ノード"
    HELP_TEXT = (
        "ノードとパーティションの現在の状態を Slurm から取得して表示します。\n\n"
        "- **制限比較** は HAKUSAN の `spart` が使える場合、その値（現行のサイト制限）を優先表示します。\n"
        "- `spart` が無い場合、sinfo/scontrol だけでは確定できないユーザー上限は空欄です。\n"
        "- 講習資料の表（p.38–39）は2026年4月時点の説明値で、判定には使いません。"
    )
    COMMANDS = ("scontrol show node -o", "scontrol show partition -o", "spart")

    def compose(self) -> ComposeResult:
        with TabbedContent(id="nodes-tabs"):
            with TabPane("ノード一覧", id="nodes-list"):
                with Horizontal(classes="toolbar"):
                    yield Select([("すべて", "all"), ("CPU", "CPU"), ("GPU", "GPU"), ("VM", "VM"),
                                  ("不明", "不明")], value="all", allow_blank=False,
                                 id="nodes-kind", classes="filter")
                    yield Input(placeholder="/ ノード名・状態で検索", id="nodes-search",
                                classes="search")
                yield DataTable(id="nodes-table", cursor_type="row", zebra_stripes=True)
            with TabPane("パーティション一覧", id="nodes-partitions"):
                with Horizontal(classes="toolbar"):
                    yield Button("このパーティションでジョブ投入", id="use-partition",
                                 variant="primary")
                yield DataTable(id="partitions-table", cursor_type="row", zebra_stripes=True)
            with TabPane("制限比較 (spart)", id="nodes-limits"):
                with Horizontal(classes="toolbar"):
                    yield Button("spart 原文を表示", id="spart-raw")
                yield Static(id="spart-note", classes="hint")
                yield DataTable(id="limits-table", cursor_type="row", zebra_stripes=True)

    def update_view(self) -> None:
        self._update_nodes()
        fill_table(self.query_one("#partitions-table", DataTable), PART_COLUMNS,
                   [partition_row(p, self.ctx.nodes()) for p in self.ctx.partitions()])
        self._update_limits()

    def _update_nodes(self) -> None:
        kind = self.query_one("#nodes-kind", Select).value
        query = self.query_one("#nodes-search", Input).value
        nodes = [n for n in self.ctx.nodes()
                 if (kind == "all" or node_kind(n) == kind)
                 and matches(query, n.name, n.state_raw, ",".join(n.partitions))]
        fill_table(self.query_one("#nodes-table", DataTable), NODE_COLUMNS,
                   [node_row(n) for n in nodes])

    def _update_limits(self) -> None:
        table = self.ctx.spart()
        note = self.query_one("#spart-note", Static)
        limits = self.query_one("#limits-table", DataTable)
        if table is None:
            note.update("spart が利用できません。sinfo/scontrol の基本情報のみです（ユーザー上限は空欄）。")
            fill_table(limits, ("パーティション", "最大時間(Slurm)", "ユーザー上限"),
                       [(p.name, (p.name, fmt_duration(p.max_time_seconds), ""))
                        for p in self.ctx.partitions()])
            return
        if not table.parsed:
            note.update("spart の出力を表として解析できませんでした。「原文を表示」で確認してください。")
            return
        note.update(Text("spart（サイトコマンド）の現行値。列の意味はサイトのドキュメントを参照。"))
        limits.clear(columns=True)
        fill_table(limits, table.headers,
                   [(str(i), tuple(r.values())) for i, r in enumerate(table.rows)])

    def on_select_changed(self, _event: Select.Changed) -> None:
        self._update_nodes()

    def on_input_changed(self, _event: Input.Changed) -> None:
        self._update_nodes()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "use-partition":
            name = selected_key(self.query_one("#partitions-table", DataTable))
            if name:
                self.happ.use_partition(name)
        elif event.button.id == "spart-raw":
            table = self.ctx.spart()
            self.app.push_screen(TextScreen("spart 原文", table.raw if table else "spart なし"))
