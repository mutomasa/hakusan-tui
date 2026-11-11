"""画面間で共有する状態（アダプター・設定・スナップショット）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hakusan_tui.adapters.base import ClusterAdapter
from hakusan_tui.config import Config
from hakusan_tui.models import Capabilities, HistoryRecord, Job, Node, Partition, SpartTable
from hakusan_tui.services.logs import LogView, read_log_tail, sanitize_terminal_text
from hakusan_tui.services.refresh import Snapshot, SnapshotStore

JOBS, NODES, PARTITIONS, HISTORY, START, SPART = (
    "jobs", "nodes", "partitions", "history", "start", "spart"
)


@dataclass
class AppContext:
    config: Config
    adapter: ClusterAdapter
    store: SnapshotStore = field(default_factory=SnapshotStore)
    caps: Capabilities = field(default_factory=Capabilities)
    history_days: int = 7

    @property
    def read_only(self) -> bool:
        return self.config.safety.read_only

    @property
    def writable(self) -> bool:
        """書き込み操作を実行できるか（読み取り専用・デモでは False）。"""
        return not self.read_only and self.adapter.executes_commands

    @property
    def user(self) -> str:
        return self.adapter.current_user

    def snapshot(self, key: str) -> Snapshot[Any]:
        return self.store.get(key)

    def _value(self, key: str, default: Any) -> Any:
        value = self.store.get(key).value
        return default if value is None else value

    def jobs(self) -> list[Job]:
        return self._value(JOBS, [])

    def my_jobs(self) -> list[Job]:
        return [j for j in self.jobs() if j.user == self.user]

    def nodes(self) -> list[Node]:
        return self._value(NODES, [])

    def partitions(self) -> list[Partition]:
        return self._value(PARTITIONS, [])

    def partitions_or_none(self) -> list[Partition] | None:
        return self.store.get(PARTITIONS).value

    def history(self) -> list[HistoryRecord]:
        return self._value(HISTORY, [])

    def start_estimates(self) -> dict[str, Any]:
        return self._value(START, {})

    def spart(self) -> SpartTable | None:
        return self.store.get(SPART).value

    def read_log(self, path: str | None) -> LogView:
        reader = getattr(self.adapter, "read_demo_log", None)
        if reader is not None:
            return LogView(path or "", sanitize_terminal_text(reader(path or "")), False)
        return read_log_tail(path)
