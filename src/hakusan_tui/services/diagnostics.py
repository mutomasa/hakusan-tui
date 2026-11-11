"""軽量な環境診断（ログインノードに負荷をかけない）。"""

from __future__ import annotations

import getpass
import socket
from dataclasses import dataclass

from hakusan_tui.adapters.base import ClusterAdapter
from hakusan_tui.adapters.hakusan import LOGIN_HOSTS
from hakusan_tui.models import Capabilities


@dataclass(frozen=True)
class DiagnosticItem:
    name: str
    status: str  # OK / NG / 注意 / 情報
    detail: str


def _yes_no(flag: bool, ok_text: str, ng_text: str) -> tuple[str, str]:
    return ("OK", ok_text) if flag else ("NG", ng_text)


def diagnose(adapter: ClusterAdapter, caps: Capabilities) -> list[DiagnosticItem]:
    host = socket.gethostname() if adapter.executes_commands else adapter.hostname
    items = [
        DiagnosticItem("ホスト名", "情報", host),
        DiagnosticItem("ユーザー", "情報", adapter.current_user or getpass.getuser()),
        DiagnosticItem("モード", "情報", "デモ（コマンド非実行）" if adapter.mode == "demo" else "Slurm CLI"),
        _login_host_item(host),
        DiagnosticItem("Slurm", *_yes_no(caps.slurm_available, caps.slurm_version or "応答あり",
                                         "; ".join(caps.notes) or "sinfo が応答しません")),
        DiagnosticItem("squeue --json", *_yes_no(caps.squeue_json, "利用可能",
                                                 "利用不可（テキスト形式で取得）")),
        DiagnosticItem("sacct（履歴）", *_yes_no(caps.sacct, "利用可能", "見つかりません")),
        DiagnosticItem("sstat（実行中統計）", *_yes_no(caps.sstat, "利用可能", "見つかりません")),
        DiagnosticItem("spart（HAKUSAN）", *_yes_no(caps.spart, "利用可能", "見つかりません（sinfo/scontrolのみ）")),
        DiagnosticItem("module", *_yes_no(caps.module, "利用可能", "シェル関数が見つかりません")),
        DiagnosticItem("PBS互換ラッパー", "OK" if caps.pbs_wrappers else "情報",
                       ", ".join(caps.pbs_wrappers) or "未検出"),
    ]
    return items


def _login_host_item(host: str) -> DiagnosticItem:
    short = host.split(".")[0]
    if short in LOGIN_HOSTS:
        return DiagnosticItem("実行場所", "注意",
                              "ログインノードです。計算・コンパイルはジョブとして実行してください")
    return DiagnosticItem("実行場所", "情報", "既知のログインノード名ではありません。ログインノードでは重い処理をしないでください")


def format_report(items: list[DiagnosticItem]) -> str:
    width = max(len(i.name) for i in items) + 2
    return "\n".join(f"[{i.status:^4}] {i.name:<{width}} {i.detail}" for i in items)
