"""クラスタアダプターの Protocol。UI はこのインターフェースだけに依存する。"""

from __future__ import annotations

from typing import Protocol

from hakusan_tui.models import (
    Capabilities,
    CommandResult,
    HistoryRecord,
    Job,
    Node,
    Partition,
    SpartTable,
)


class AdapterError(RuntimeError):
    """取得に失敗した（利用者向けメッセージを持つ）。"""


class ClusterAdapter(Protocol):
    mode: str  # "slurm" | "demo"
    current_user: str
    hostname: str
    executes_commands: bool  # False ならコマンドを一切実行しない（デモ）

    async def detect_capabilities(self) -> Capabilities: ...

    async def get_jobs(self) -> list[Job]: ...

    async def get_nodes(self) -> list[Node]: ...

    async def get_partitions(self) -> list[Partition]: ...

    async def get_job_detail(self, job_id: str) -> Job | None: ...

    async def get_history(self, days: int, max_records: int) -> list[HistoryRecord]: ...

    async def get_spart(self) -> SpartTable | None: ...

    async def get_start_estimates(self) -> dict[str, object]: ...

    async def get_sstat(self, job_id: str) -> CommandResult: ...

    async def submit_job(self, script_path: str, test_only: bool = False) -> CommandResult: ...

    async def cancel_job(self, job_id: str) -> CommandResult: ...

    async def run_readonly_tool(self, name: str, args: tuple[str, ...] = ()) -> CommandResult: ...

    def take_warnings(self) -> list[str]: ...
