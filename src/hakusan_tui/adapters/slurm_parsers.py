"""Slurm CLI 出力のパーサー。

UI に生出力を渡さず、ここで共通モデルへ正規化する。
壊れた行は推測補完せず、``warnings`` に記録してスキップする。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from hakusan_tui.models import HistoryRecord, Job, JobStep, Node, Partition

# テキスト出力の区切り。ユーザー入力（ジョブ名）に出現しにくい ASCII Unit Separator。
FIELD_SEP = "\x1f"

KNOWN_STATES = frozenset(
    {
        "PENDING", "RUNNING", "COMPLETING", "COMPLETED", "FAILED", "CANCELLED",
        "TIMEOUT", "OUT_OF_MEMORY", "SUSPENDED", "NODE_FAIL", "PREEMPTED", "REQUEUED",
    }
)

_UNSET_VALUES = frozenset({"", "(null)", "N/A", "None", "Unknown", "UNLIMITED", "INVALID"})


class ParseError(ValueError):
    """出力形式が想定外で解析できない。"""


# ---------------------------------------------------------------- 基本変換


def normalize_state(raw: str | None) -> str:
    """``CANCELLED by 123`` や ``RUNNING+...`` を正規化。未知は ``UNKNOWN``。"""
    if not raw:
        return "UNKNOWN"
    head = raw.strip().split()[0].split("+")[0].upper()
    if head == "OOM":
        head = "OUT_OF_MEMORY"
    return head if head in KNOWN_STATES else "UNKNOWN"


def parse_duration(text: str | None) -> int | None:
    """``[D-]HH:MM:SS`` / ``MM:SS`` / ``MM`` を秒へ。無制限・不明は ``None``。"""
    if text is None:
        return None
    text = text.strip()
    if text in _UNSET_VALUES or text.upper() in {"INFINITE", "NONE", "NOT_SET"}:
        return None
    days = 0
    if "-" in text:
        day_part, text = text.split("-", 1)
        if not day_part.isdigit():
            return None
        days = int(day_part)
    parts = text.split(":")
    if not all(p.isdigit() for p in parts) or not 1 <= len(parts) <= 3:
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 1:
        seconds = nums[0] * 60 if days == 0 else nums[0] * 3600
    elif len(nums) == 2:
        seconds = nums[0] * 60 + nums[1] if days == 0 else nums[0] * 3600 + nums[1] * 60
    else:
        seconds = nums[0] * 3600 + nums[1] * 60 + nums[2]
    return days * 86400 + seconds


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    base = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}-{base}" if days else base


_MEM_UNITS = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024}


def parse_memory_mib(text: str | None) -> float | None:
    """``3232K`` / ``250M`` / ``2G`` を MiB へ。単位なしは MiB とみなす（Slurm既定）。"""
    if text is None:
        return None
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)[iB]*\s*", text, re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1)) * _MEM_UNITS[(m.group(2) or "M").upper()]


def parse_datetime(text: str | None) -> datetime | None:
    if not text or text in _UNSET_VALUES:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    return int(text) if text.isdigit() else None


def parse_tres(text: str | None) -> dict[str, str]:
    """``cpu=1,mem=250M,gres/gpu=1`` → dict。"""
    if not text or text in _UNSET_VALUES:
        return {}
    result: dict[str, str] = {}
    for item in text.split(","):
        key, sep, value = item.partition("=")
        if sep and key:
            result[key.strip()] = value.strip()
    return result


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value in _UNSET_VALUES else value


def split_job_reason(nodelist_reason: str | None) -> tuple[str | None, str | None]:
    """``NODELIST(REASON)`` 列を (ノード, 理由) に分離する。"""
    if not nodelist_reason:
        return None, None
    text = nodelist_reason.strip()
    if text.startswith("(") and text.endswith(")"):
        return None, clean(text[1:-1])
    return clean(text), None


# ---------------------------------------------------------------- scontrol -o


_KV_PATTERN = re.compile(r"(?:^|\s)([A-Za-z][\w/:.\[\]]*)=(.*?)(?=\s+[A-Za-z][\w/:.\[\]]*=|\s*$)")


def parse_key_values(line: str) -> dict[str, str]:
    """``scontrol show ... -o`` の 1 行を dict へ。値に空白があっても次のキーまでを値とする。"""
    return {m.group(1): m.group(2).strip() for m in _KV_PATTERN.finditer(line.strip())}


def _user_from_userid(text: str | None) -> str:
    """``testuser(2001)`` → ``testuser``。"""
    if not text:
        return ""
    return text.split("(", 1)[0]


def parse_scontrol_jobs(text: str) -> list[Job]:
    jobs = []
    for line in text.splitlines():
        if line.strip().startswith("JobId="):
            jobs.append(job_from_scontrol(parse_key_values(line)))
    return jobs


def job_from_scontrol(kv: dict[str, str]) -> Job:
    state_raw = kv.get("JobState", "")
    return Job(
        job_id=kv.get("JobId", ""),
        user=_user_from_userid(kv.get("UserId")),
        name=kv.get("JobName", ""),
        partition=clean(kv.get("Partition")),
        state_raw=state_raw,
        state_normalized=normalize_state(state_raw),
        reason=clean(kv.get("Reason")),
        elapsed_seconds=parse_duration(kv.get("RunTime")),
        time_limit_seconds=parse_duration(kv.get("TimeLimit")),
        n_nodes=parse_int(kv.get("NumNodes", "").split("-")[0]),
        n_cpus=parse_int(kv.get("NumCPUs", "").split("-")[0]),
        node_list=clean(kv.get("NodeList")),
        requested_tres=parse_tres(kv.get("ReqTRES")),
        allocated_tres=parse_tres(kv.get("AllocTRES")),
        tres_per_node=clean(kv.get("TresPerNode")),
        submit_time=parse_datetime(kv.get("SubmitTime")),
        start_time=parse_datetime(kv.get("StartTime")),
        work_dir=clean(kv.get("WorkDir")),
        stdout_path=clean(kv.get("StdOut")),
        stderr_path=clean(kv.get("StdErr")),
        exit_code=clean(kv.get("ExitCode")),
    )


def parse_scontrol_nodes(text: str) -> list[Node]:
    nodes = []
    for line in text.splitlines():
        if line.strip().startswith("NodeName="):
            nodes.append(node_from_scontrol(parse_key_values(line)))
    return nodes


def node_from_scontrol(kv: dict[str, str]) -> Node:
    partitions = clean(kv.get("Partitions"))
    return Node(
        name=kv.get("NodeName", ""),
        state_raw=kv.get("State", "UNKNOWN"),
        partitions=tuple(partitions.split(",")) if partitions else (),
        cpus_total=parse_int(kv.get("CPUTot")),
        cpus_allocated=parse_int(kv.get("CPUAlloc")),
        memory_total_mib=parse_int(kv.get("RealMemory")),
        memory_allocated_mib=parse_int(kv.get("AllocMem")),
        gres_raw=clean(kv.get("Gres")),
        gres_used_raw=clean(kv.get("GresUsed")),
        cfg_tres=parse_tres(kv.get("CfgTRES")),
        alloc_tres=parse_tres(kv["AllocTRES"]) if "AllocTRES" in kv else None,
        reason=clean(kv.get("Reason")),
    )


def parse_scontrol_partitions(text: str) -> list[Partition]:
    parts = []
    for line in text.splitlines():
        if line.strip().startswith("PartitionName="):
            parts.append(partition_from_scontrol(parse_key_values(line)))
    return parts


def expand_hostlist(expr: str | None) -> tuple[str, ...]:
    """``node[01-03,05],gpu1`` を展開する（ゼロ埋め保持）。"""
    if not expr or expr in _UNSET_VALUES:
        return ()
    names: list[str] = []
    for token in re.findall(r"[^,\[]+(?:\[[^\]]*\])?[^,]*", expr):
        names.extend(_expand_token(token.strip()))
    return tuple(n for n in names if n)


def _expand_token(token: str) -> list[str]:
    m = re.fullmatch(r"(.*?)\[([^\]]+)\](.*)", token)
    if not m:
        return [token]
    prefix, ranges, suffix = m.groups()
    out = []
    for part in ranges.split(","):
        lo, _, hi = part.partition("-")
        if not hi:
            out.append(f"{prefix}{lo}{suffix}")
            continue
        width = len(lo)
        out.extend(f"{prefix}{i:0{width}d}{suffix}" for i in range(int(lo), int(hi) + 1))
    return out


def partition_from_scontrol(kv: dict[str, str]) -> Partition:
    state = clean(kv.get("State"))
    return Partition(
        name=kv.get("PartitionName", ""),
        available=(state == "UP") if state else None,
        max_time_seconds=parse_duration(kv.get("MaxTime")),
        total_nodes=parse_int(kv.get("TotalNodes")),
        state_summary=state,
        is_default=kv.get("Default") == "YES",
        node_names=expand_hostlist(kv.get("Nodes")),
        total_cpus=parse_int(kv.get("TotalCPUs")),
        tres=parse_tres(kv.get("TRES")),
    )


# ---------------------------------------------------------------- squeue --json


def _num(value: Any) -> int | None:
    """data_parser の ``{"set":..,"infinite":..,"number":..}`` と素の数値の両対応。"""
    if isinstance(value, dict):
        if not value.get("set", False) or value.get("infinite", False):
            return None
        value = value.get("number")
    if isinstance(value, bool):
        return None
    return int(value) if isinstance(value, int | float) else None


def _epoch(value: Any) -> datetime | None:
    n = _num(value)
    return datetime.fromtimestamp(n) if n else None


def _state_from_json(value: Any) -> str:
    if isinstance(value, list):
        return "+".join(str(v) for v in value)
    return str(value or "")


def _exit_code_from_json(value: Any) -> str | None:
    if not isinstance(value, dict):
        return clean(str(value)) if value is not None else None
    code = _num(value.get("return_code"))
    signal = _num((value.get("signal") or {}).get("id"))
    if code is None:
        return None
    return f"{code}:{signal or 0}"


def load_json_document(text: str) -> dict[str, Any]:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSONとして解析できません: {exc}") from exc
    if not isinstance(doc, dict):
        raise ParseError("JSONの最上位がオブジェクトではありません")
    return doc


def parse_squeue_json(text: str, now: datetime | None = None) -> list[Job]:
    doc = load_json_document(text)
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ParseError("squeue JSONに jobs 配列がありません")
    return [job_from_json(j, now) for j in jobs if isinstance(j, dict)]


def _json_job_id(j: dict[str, Any]) -> str:
    job_id = str(j.get("job_id", ""))
    array_id = _num(j.get("array_job_id"))
    task_id = _num(j.get("array_task_id"))
    if array_id and task_id is not None and str(array_id) != job_id:
        return f"{array_id}_{task_id}"
    return job_id


def _json_elapsed(j: dict[str, Any], state: str, now: datetime) -> int | None:
    start = _epoch(j.get("start_time"))
    if state == "PENDING" or start is None:
        return 0 if state == "PENDING" else None
    end = _epoch(j.get("end_time"))
    reference = now if state in {"RUNNING", "COMPLETING"} or end is None else end
    return max(0, int((reference - start).total_seconds()))


def job_from_json(j: dict[str, Any], now: datetime | None = None) -> Job:
    state_raw = _state_from_json(j.get("job_state"))
    state = normalize_state(state_raw)
    limit_minutes = _num(j.get("time_limit"))
    return Job(
        job_id=_json_job_id(j),
        user=str(j.get("user_name") or ""),
        name=str(j.get("name") or ""),
        partition=clean(j.get("partition")),
        state_raw=state_raw,
        state_normalized=state,
        reason=clean(j.get("state_reason")),
        elapsed_seconds=_json_elapsed(j, state, now or datetime.now()),
        time_limit_seconds=limit_minutes * 60 if limit_minutes is not None else None,
        n_nodes=_num(j.get("node_count")),
        n_cpus=_num(j.get("cpus")),
        node_list=clean(j.get("nodes")),
        requested_tres=parse_tres(j.get("tres_req_str")),
        allocated_tres=parse_tres(j.get("tres_alloc_str")),
        tres_per_node=clean(j.get("tres_per_node")),
        submit_time=_epoch(j.get("submit_time")),
        start_time=_epoch(j.get("start_time")) if state != "PENDING" else None,
        work_dir=clean(j.get("current_working_directory")),
        stdout_path=clean(j.get("standard_output")),
        stderr_path=clean(j.get("standard_error")),
        exit_code=_exit_code_from_json(j.get("exit_code")),
    )


def json_slurm_version(text: str) -> str | None:
    try:
        meta = load_json_document(text).get("meta", {})
    except ParseError:
        return None
    return (meta.get("slurm") or {}).get("release")


# ---------------------------------------------------------------- squeue テキスト

# ジョブ名は最後に置き、名前中に区切り文字があっても他の列を壊さない。
SQUEUE_FIELDS = ("%i", "%u", "%P", "%T", "%M", "%l", "%D", "%C", "%b", "%R", "%j")
SQUEUE_FORMAT = FIELD_SEP.join(SQUEUE_FIELDS)


def parse_squeue_text(text: str, warnings: list[str] | None = None) -> list[Job]:
    jobs = []
    for line in text.splitlines():
        if not line.strip():
            continue
        job = _job_from_squeue_line(line)
        if job is None:
            if warnings is not None:
                warnings.append(f"解析できない squeue 行をスキップ: {line[:120]!r}")
            continue
        jobs.append(job)
    return jobs


def _job_from_squeue_line(line: str) -> Job | None:
    parts = line.split(FIELD_SEP, len(SQUEUE_FIELDS) - 1)
    if len(parts) != len(SQUEUE_FIELDS):
        return None
    job_id, user, partition, state, elapsed, limit, nodes, cpus, tres, nodelist, name = parts
    node_list, reason = split_job_reason(nodelist)
    return Job(
        job_id=job_id.strip(),
        user=user.strip(),
        name=name,
        partition=clean(partition),
        state_raw=state.strip(),
        state_normalized=normalize_state(state),
        reason=reason,
        elapsed_seconds=parse_duration(elapsed),
        time_limit_seconds=parse_duration(limit),
        n_nodes=parse_int(nodes),
        n_cpus=parse_int(cpus),
        node_list=node_list,
        tres_per_node=clean(tres),
    )


def parse_squeue_start(text: str) -> dict[str, datetime]:
    """``squeue --start -h -o %i<SEP>%S`` → {job_id: 推定開始}。"""
    result = {}
    for line in text.splitlines():
        job_id, sep, start = line.replace("|", FIELD_SEP).partition(FIELD_SEP)
        when = parse_datetime(start.strip()) if sep else None
        if when is not None:
            result[job_id.strip()] = when
    return result


# ---------------------------------------------------------------- sacct

# JobName は最後（区切り文字を含み得るため maxsplit で保護）。
SACCT_FIELDS = (
    "JobID", "User", "Partition", "State", "ExitCode", "Elapsed", "AllocCPUS",
    "AllocTRES", "ReqTRES", "MaxRSS", "Start", "End", "Submit", "WorkDir", "JobName",
)


def parse_sacct(text: str, warnings: list[str] | None = None) -> list[HistoryRecord]:
    """``sacct -n -P --delimiter=<SEP> --format=SACCT_FIELDS`` を親子にまとめる。"""
    rows = _sacct_rows(text, warnings)
    parents: dict[str, dict[str, str]] = {}
    steps: dict[str, list[JobStep]] = {}
    for row in rows:
        job_id, dot, _ = row["JobID"].partition(".")
        if dot:
            steps.setdefault(job_id, []).append(_step_from_row(row))
        else:
            parents[job_id] = row
    return [_history_from_row(row, tuple(steps.get(jid, ()))) for jid, row in parents.items()]


def _sacct_rows(text: str, warnings: list[str] | None) -> Iterable[dict[str, str]]:
    sep = FIELD_SEP if FIELD_SEP in text else "|"
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(sep, len(SACCT_FIELDS) - 1)
        if len(parts) != len(SACCT_FIELDS):
            if warnings is not None:
                warnings.append(f"解析できない sacct 行をスキップ: {line[:120]!r}")
            continue
        yield dict(zip(SACCT_FIELDS, parts, strict=True))


def _step_from_row(row: dict[str, str]) -> JobStep:
    return JobStep(
        step_id=row["JobID"],
        name=row["JobName"],
        state_raw=row["State"],
        state_normalized=normalize_state(row["State"]),
        exit_code=clean(row["ExitCode"]),
        elapsed_seconds=parse_duration(row["Elapsed"]),
        alloc_cpus=parse_int(row["AllocCPUS"]),
        alloc_tres=parse_tres(row["AllocTRES"]),
        max_rss_mib=parse_memory_mib(row["MaxRSS"]) if row["MaxRSS"] else None,
    )


def _history_from_row(row: dict[str, str], steps: tuple[JobStep, ...]) -> HistoryRecord:
    return HistoryRecord(
        job_id=row["JobID"],
        name=row["JobName"],
        user=clean(row["User"]),
        partition=clean(row["Partition"]),
        state_raw=row["State"],
        state_normalized=normalize_state(row["State"]),
        exit_code=clean(row["ExitCode"]),
        elapsed_seconds=parse_duration(row["Elapsed"]),
        alloc_cpus=parse_int(row["AllocCPUS"]),
        alloc_tres=parse_tres(row["AllocTRES"]),
        req_tres=parse_tres(row["ReqTRES"]),
        start_time=parse_datetime(row["Start"]),
        end_time=parse_datetime(row["End"]),
        submit_time=parse_datetime(row["Submit"]),
        work_dir=clean(row["WorkDir"]),
        steps=steps,
    )


# ---------------------------------------------------------------- sbatch


def parse_sbatch_parsable(stdout: str) -> str | None:
    """``sbatch --parsable`` の出力 ``123`` または ``123;cluster`` からジョブIDを取り出す。"""
    first = stdout.strip().splitlines()[0] if stdout.strip() else ""
    job_id = first.split(";", 1)[0].strip()
    return job_id if re.fullmatch(r"\d+", job_id) else None


def top_level_job_id(job_id: str) -> str:
    """``123.batch`` / ``123_4`` / ``123+0`` → 操作対象のトップレベルID。配列タスクは保持。"""
    base = job_id.split(".", 1)[0].split("+", 1)[0]
    return base
