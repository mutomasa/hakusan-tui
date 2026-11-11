"""表示用の整形（None は「—」や「未取得」で表す。0 と混同しない）。"""

from __future__ import annotations

from datetime import datetime

from rich.cells import cell_len

from hakusan_tui.adapters.slurm_parsers import format_duration
from hakusan_tui.i18n import job_state_display
from hakusan_tui.models import Job

DASH = "—"


def fmt_int(value: int | None) -> str:
    return DASH if value is None else str(value)


def fmt_time(value: datetime | None) -> str:
    return DASH if value is None else value.strftime("%m/%d %H:%M")


def fmt_clock(value: datetime | None) -> str:
    return "未取得" if value is None else value.strftime("%H:%M:%S")


def fmt_duration(seconds: int | None) -> str:
    return format_duration(seconds) if seconds is not None else DASH


def fmt_mib(value: float | None) -> str:
    if value is None:
        return "未確定"
    if value >= 1024:
        return f"{value / 1024:.1f}G"
    return f"{value:.0f}M"


def job_state(job: Job) -> str:
    return job_state_display(job.state_normalized, job.state_raw)


def tres_gpu_count(tres: dict[str, str]) -> int | None:
    if not tres:
        return None
    if "gres/gpu" in tres:
        value = tres["gres/gpu"]
        return int(value) if value.isdigit() else None
    return 0


def job_gpus(job: Job) -> str:
    count = tres_gpu_count(job.allocated_tres or job.requested_tres)
    if count is None and job.tres_per_node:
        return job.tres_per_node.replace("gres/", "")
    return fmt_int(count)


def job_mem(job: Job) -> str:
    tres = job.allocated_tres or job.requested_tres
    return tres.get("mem", DASH)


def job_where(job: Job) -> str:
    """実行中はノード、待機中は（理由）を表示。意味が違うので書式も分ける。"""
    if job.is_pending:
        return f"({job.reason or '理由なし'})"
    return job.node_list or DASH


def bar(allocated: int | None, total: int | None, width: int = 10) -> str:
    if allocated is None or total is None or total <= 0:
        return "[" + "?" * 3 + "]"
    filled = round(width * min(allocated, total) / total)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def pad(text: str, width: int) -> str:
    """全角文字の幅を考慮した左寄せ。"""
    return text + " " * max(0, width - cell_len(text))
