"""入力検証（許可文字のホワイトリスト）。"""

from __future__ import annotations

import re

JOB_ID_RE = re.compile(r"^\d+(?:_\d+)?$")
PARTITION_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
JOB_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")
MODULE_RE = re.compile(r"^[A-Za-z0-9_.+\-/]{1,128}$")
MEMORY_RE = re.compile(r"^\d+[KMGT]?$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
OUTPUT_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-/%~]{1,255}$")
GPU_TYPE_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

MAIL_TYPES = ("NONE", "BEGIN", "END", "FAIL", "REQUEUE", "ALL", "TIME_LIMIT", "ARRAY_TASKS")


def is_job_id(text: str) -> bool:
    return bool(JOB_ID_RE.fullmatch(text))


def is_partition(text: str) -> bool:
    return bool(PARTITION_RE.fullmatch(text))


def is_module_name(text: str) -> bool:
    return bool(MODULE_RE.fullmatch(text)) and ".." not in text


def has_control_chars(text: str) -> bool:
    """改行・制御文字を含むか（#SBATCH 行への注入防止）。"""
    return bool(_CONTROL_RE.search(text)) or "\n" in text or "\r" in text
