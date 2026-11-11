"""ジョブログの安全な末尾表示。

- 通常ファイルのみ、読み取り可能な範囲だけ読む。シンボリックリンクは解決後に確認。
- 末尾 1MiB まで。ANSI エスケープと制御文字は除去する。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

MAX_LOG_BYTES = 1024 * 1024

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-_]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class LogView:
    path: str
    text: str
    truncated: bool
    error: str | None = None


def sanitize_terminal_text(text: str) -> str:
    """ANSI エスケープ・制御文字を取り除く（改行とタブは残す）。"""
    text = _ANSI_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    return _CTRL_RE.sub("", text)


def read_log_tail(path: str | None, max_bytes: int = MAX_LOG_BYTES) -> LogView:
    if not path:
        return LogView("", "", False, "ログのパスが取得できません")
    real = os.path.realpath(os.path.expanduser(path))
    error = _check_readable(real)
    if error:
        return LogView(path, "", False, error)
    return _read_tail(path, real, max_bytes)


def _check_readable(real: str) -> str | None:
    if not os.path.exists(real):
        return "ログファイルがまだありません（待機中、または別の場所に出力）"
    if not os.path.isfile(real):
        return "通常のファイルではありません"
    if not os.access(real, os.R_OK):
        return "読み取り権限がありません"
    return None


def _read_tail(path: str, real: str, max_bytes: int) -> LogView:
    try:
        with open(real, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - max_bytes))
            data = fh.read(max_bytes)
    except OSError as exc:
        return LogView(path, "", False, f"読み込みに失敗: {exc.strerror}")
    text = sanitize_terminal_text(data.decode("utf-8", errors="replace"))
    return LogView(path, text, size > max_bytes)
