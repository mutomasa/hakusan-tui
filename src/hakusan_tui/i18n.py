"""日本語の状態名・待機理由の説明。"""

from __future__ import annotations

JOB_STATE_LABELS: dict[str, str] = {
    "PENDING": "待機中",
    "RUNNING": "実行中",
    "COMPLETING": "完了処理中",
    "COMPLETED": "完了",
    "FAILED": "失敗",
    "CANCELLED": "キャンセル",
    "TIMEOUT": "時間切れ",
    "OUT_OF_MEMORY": "メモリ不足",
    "SUSPENDED": "停止中",
    "NODE_FAIL": "ノード障害",
    "PREEMPTED": "プリエンプト",
    "REQUEUED": "再キュー",
    "UNKNOWN": "不明",
}

JOB_STATE_SHORT: dict[str, str] = {
    "PENDING": "PD",
    "RUNNING": "R",
    "COMPLETING": "CG",
    "COMPLETED": "CD",
    "FAILED": "F",
    "CANCELLED": "CA",
    "TIMEOUT": "TO",
    "OUT_OF_MEMORY": "OOM",
    "SUSPENDED": "S",
    "NODE_FAIL": "NF",
    "PREEMPTED": "PR",
    "REQUEUED": "RQ",
    "UNKNOWN": "?",
}

NODE_STATE_LABELS: dict[str, str] = {
    "IDLE": "空き",
    "MIXED": "一部使用",
    "ALLOCATED": "使用中",
    "ALLOC": "使用中",
    "COMPLETING": "完了処理中",
    "DRAIN": "受付停止",
    "DRAINING": "受付停止中",
    "DRAINED": "受付停止",
    "DOWN": "停止",
    "RESERVED": "予約",
    "MAINT": "保守",
    "FUTURE": "将来追加",
    "INVAL": "設定不整合",
    "UNKNOWN": "不明",
    "POWERED_DOWN": "電源オフ",
    "PLANNED": "予定",
}

REASON_HELP: dict[str, str] = {
    "Resources": "必要な資源（CPU/GPU/メモリ/ノード）が現在割り当てられません。空くのを待っています。",
    "Priority": "より優先度の高いジョブを先に処理しています。",
    "Dependency": "依存先のジョブの完了などを待っています。",
    "DependencyNeverSatisfied": "依存条件が満たされないため開始できません。依存先を確認してください。",
    "BeginTime": "指定された開始時刻（--begin）を待っています。",
    "JobHeldUser": "ユーザーにより保留されています。",
    "JobHeldAdmin": "管理者により保留されています。",
    "PartitionTimeLimit": "要求時間がパーティションの上限を超えています。--time を見直してください。",
    "PartitionNodeLimit": "要求ノード数がパーティションの上限を超えています。",
    "PartitionDown": "パーティションが停止しています。",
    "ReqNodeNotAvail": "要求したノードが利用できません（保守・停止など）。",
    "launch_failed_requeued_held": "起動に失敗し、保留状態で再キューされました。管理者に相談してください。",
    "None": "特記事項なし。",
}

REASON_PREFIX_HELP: dict[str, str] = {
    "QOS": "QOS（サービス品質）のポリシー・上限に関連する可能性があります。サイトの利用規則を確認してください。",
    "Assoc": "アカウント/ユーザー単位の上限（同時実行数など）に関連する可能性があります。",
    "AssocGrp": "グループ単位の上限に達している可能性があります。",
}


def job_state_label(state: str) -> str:
    return JOB_STATE_LABELS.get(state, JOB_STATE_LABELS["UNKNOWN"])


def job_state_display(state: str, raw: str | None = None) -> str:
    """``待機中 (PD)`` のような表示。未知状態は生文字列を残す。"""
    short = JOB_STATE_SHORT.get(state)
    if state == "UNKNOWN" and raw:
        return f"不明 ({raw})"
    return f"{job_state_label(state)} ({short})" if short else job_state_label(state)


def node_state_label(base_state: str) -> str:
    return NODE_STATE_LABELS.get(base_state.upper(), f"不明 ({base_state})")


def explain_reason(reason: str | None) -> str:
    """待機理由コードの日本語説明。未知の理由はコードをそのまま示す。"""
    if not reason:
        return "理由なし"
    if reason in REASON_HELP:
        return REASON_HELP[reason]
    for prefix, text in REASON_PREFIX_HELP.items():
        if reason.startswith(prefix):
            return text
    return f"未知の理由: {reason}（Slurmのドキュメントを参照してください）"
