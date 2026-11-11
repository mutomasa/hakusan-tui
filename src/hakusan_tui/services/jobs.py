"""ジョブ操作（キャンセル）の安全確認。

1. 読み取り専用・デモでは実行しない。
2. ジョブIDを検証し、トップレベルIDに正規化する。
3. 実行直前に ``scontrol`` で再取得し、所有者と状態を再検査する（TOCTOU 対策）。
"""

from __future__ import annotations

from dataclasses import dataclass

from hakusan_tui.adapters.base import AdapterError, ClusterAdapter
from hakusan_tui.adapters.slurm_parsers import top_level_job_id
from hakusan_tui.models import Job
from hakusan_tui.validation import is_job_id


@dataclass(frozen=True)
class ActionOutcome:
    ok: bool
    message: str
    executed: bool = False


def cancel_preview(job_id: str) -> str:
    return f"scancel {top_level_job_id(job_id)}"


def can_cancel(job: Job, current_user: str, read_only: bool) -> tuple[bool, str]:
    """UI のボタン表示判定（実行時には ``JobActionService`` で再検査する）。"""
    if read_only:
        return False, "読み取り専用モードではキャンセルできません"
    if job.user != current_user:
        return False, "他のユーザーのジョブは操作できません"
    if not job.is_active:
        return False, "終了済みのジョブはキャンセルできません"
    return True, ""


class JobActionService:
    def __init__(self, adapter: ClusterAdapter, read_only: bool):
        self._adapter = adapter
        self._read_only = read_only

    async def cancel(self, job_id: str) -> ActionOutcome:
        target = top_level_job_id(job_id)
        refusal = await self._check_cancel(target)
        if refusal is not None:
            return refusal
        result = await self._adapter.cancel_job(target)
        if not result.ok:
            return ActionOutcome(False, f"キャンセルに失敗: {result.error_message()}")
        return ActionOutcome(True, f"ジョブ {target} にキャンセルを要求しました", executed=True)

    async def _check_cancel(self, job_id: str) -> ActionOutcome | None:
        if self._read_only:
            return ActionOutcome(False, "読み取り専用モードのため実行しません")
        if not self._adapter.executes_commands:
            return ActionOutcome(False, "デモモードのため実行しません")
        if not is_job_id(job_id):
            return ActionOutcome(False, f"ジョブIDが不正です: {job_id!r}")
        try:
            job = await self._adapter.get_job_detail(job_id)
        except AdapterError as exc:
            return ActionOutcome(False, f"ジョブ情報を再取得できません: {exc}")
        if job is None:
            return ActionOutcome(False, "ジョブが見つかりません（終了済みの可能性）")
        ok, reason = can_cancel(job, self._adapter.current_user, self._read_only)
        return None if ok else ActionOutcome(False, reason)
