"""統一データモデル。

数値の ``None`` は「未取得・非対応」を表し、``0`` とは区別する。
メモリは MiB、時間は秒に統一する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

JobState = Literal[
    "PENDING",
    "RUNNING",
    "COMPLETING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "SUSPENDED",
    "NODE_FAIL",
    "PREEMPTED",
    "REQUEUED",
    "UNKNOWN",
]

ACTIVE_STATES: frozenset[str] = frozenset({"PENDING", "RUNNING", "COMPLETING", "SUSPENDED"})

ResourceUnit = Literal["physical_gpu", "mig_instance", "virtual_fraction", "unknown"]


@dataclass(frozen=True)
class Job:
    job_id: str
    user: str
    name: str
    partition: str | None
    state_raw: str
    state_normalized: str
    reason: str | None = None
    elapsed_seconds: int | None = None
    time_limit_seconds: int | None = None
    n_nodes: int | None = None
    n_cpus: int | None = None
    node_list: str | None = None
    requested_tres: dict[str, str] = field(default_factory=dict)
    allocated_tres: dict[str, str] = field(default_factory=dict)
    tres_per_node: str | None = None
    submit_time: datetime | None = None
    start_time: datetime | None = None
    work_dir: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    exit_code: str | None = None

    @property
    def is_pending(self) -> bool:
        return self.state_normalized == "PENDING"

    @property
    def is_running(self) -> bool:
        return self.state_normalized == "RUNNING"

    @property
    def is_active(self) -> bool:
        return self.state_normalized in ACTIVE_STATES


@dataclass(frozen=True)
class JobStep:
    step_id: str
    name: str
    state_raw: str
    state_normalized: str
    exit_code: str | None = None
    elapsed_seconds: int | None = None
    alloc_cpus: int | None = None
    alloc_tres: dict[str, str] = field(default_factory=dict)
    max_rss_mib: float | None = None


@dataclass(frozen=True)
class HistoryRecord:
    """sacct のジョブ単位（親行）とそのステップ。"""

    job_id: str
    name: str
    user: str | None
    partition: str | None
    state_raw: str
    state_normalized: str
    exit_code: str | None
    elapsed_seconds: int | None
    alloc_cpus: int | None
    alloc_tres: dict[str, str]
    req_tres: dict[str, str]
    start_time: datetime | None
    end_time: datetime | None
    submit_time: datetime | None
    work_dir: str | None
    steps: tuple[JobStep, ...] = ()

    @property
    def max_rss_mib(self) -> float | None:
        """ステップの最大MaxRSS。親行には MaxRSS が無いことが多い。"""
        values = [s.max_rss_mib for s in self.steps if s.max_rss_mib is not None]
        return max(values) if values else None


@dataclass(frozen=True)
class Node:
    name: str
    state_raw: str
    partitions: tuple[str, ...]
    cpus_total: int | None = None
    cpus_allocated: int | None = None
    memory_total_mib: int | None = None
    memory_allocated_mib: int | None = None
    gres_raw: str | None = None
    gres_used_raw: str | None = None
    cfg_tres: dict[str, str] = field(default_factory=dict)
    # None は「AllocTRES が出力に無い（不明）」、{} は「割当なし」。
    alloc_tres: dict[str, str] | None = None
    reason: str | None = None

    @property
    def base_state(self) -> str:
        """``MIXED+DRAIN`` や ``IDLE*`` から主状態だけを取り出す。"""
        return self.state_raw.split("+")[0].rstrip("*~#!%$@^-").upper()


@dataclass(frozen=True)
class Partition:
    name: str
    available: bool | None
    max_time_seconds: int | None
    total_nodes: int | None
    state_summary: str | None
    is_default: bool = False
    node_names: tuple[str, ...] = ()
    total_cpus: int | None = None
    tres: dict[str, str] = field(default_factory=dict)
    site_limits: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GpuAllocation:
    node_name: str
    gpu_type: str
    resource_unit: str
    total: int | None
    allocated: int | None
    free: int | None
    source: str
    partitions: tuple[str, ...] = ()
    node_state: str = ""


@dataclass(frozen=True)
class GpuGroupSummary:
    group: str
    resource_unit: str
    total: int | None
    allocated: int | None
    free: int | None
    node_count: int


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    truncated: bool = False
    not_found: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.not_found

    def error_message(self) -> str:
        """利用者向けの短いエラー文。"""
        if self.not_found:
            return f"コマンドが見つかりません: {self.argv[0]}"
        if self.timed_out:
            return f"タイムアウト: {' '.join(self.argv)}"
        return (self.stderr or self.stdout).strip()[:500] or f"終了コード {self.returncode}"


@dataclass(frozen=True)
class Capabilities:
    slurm_available: bool = False
    slurm_version: str | None = None
    squeue_json: bool = False
    sacct: bool = False
    sstat: bool = False
    spart: bool = False
    module: bool = False
    pbs_wrappers: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpartTable:
    """spart の出力。解析できなかった場合も原文を保持する。"""

    raw: str
    headers: tuple[str, ...] = ()
    rows: tuple[dict[str, str], ...] = ()
    parsed: bool = False
