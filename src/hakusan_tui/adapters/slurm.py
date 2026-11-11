"""公式 Slurm CLI を使うアダプター。"""

from __future__ import annotations

import getpass
import os
import shutil
import socket

from hakusan_tui.adapters import slurm_parsers as p
from hakusan_tui.adapters.base import AdapterError
from hakusan_tui.adapters.hakusan import merge_spart_limits, parse_spart
from hakusan_tui.adapters.tools import PBS_COMMANDS, build_tool_argv
from hakusan_tui.models import (
    Capabilities,
    CommandResult,
    HistoryRecord,
    Job,
    Node,
    Partition,
    SpartTable,
)
from hakusan_tui.services.command_runner import AsyncCommandRunner, CommandRunner
from hakusan_tui.validation import is_job_id

SACCT_TIMEOUT = 15.0
SPART_TIMEOUT = 10.0
SUBMIT_TIMEOUT = 30.0
JSON_TIMEOUT = 15.0


def json_fallback_message(result: CommandResult, exc: Exception) -> str:
    """原因（出力の切り詰め / 壊れたJSON）が分かる警告文。出力内容そのものは含めない。"""
    size = len(result.stdout.encode("utf-8", errors="replace"))
    if result.truncated:
        cause = f"出力が上限を超えて切り詰められました（{size} バイトで打ち切り）"
    else:
        cause = f"Slurm の JSON が不正です（{size} バイト、{exc}）"
    return f"squeue --json を解析できないためテキスト形式に切替: {cause}"


class SlurmAdapter:
    mode = "slurm"
    executes_commands = True

    def __init__(
        self,
        runner: CommandRunner | None = None,
        user: str | None = None,
        which=shutil.which,
    ):
        self._runner = runner or AsyncCommandRunner()
        self._which = which
        self.current_user = user or getpass.getuser()
        self.hostname = socket.gethostname()
        self._use_json = False
        self._capabilities = Capabilities()
        self._warnings: list[str] = []

    # ------------------------------------------------------------ 共通

    async def _run(self, argv: list[str], timeout: float = 5.0, cwd: str | None = None):
        return await self._runner.run(argv, timeout=timeout, cwd=cwd)

    async def _run_ok(self, argv: list[str], timeout: float = 5.0) -> str:
        result = await self._run(argv, timeout)
        if not result.ok:
            raise AdapterError(result.error_message())
        if result.truncated:
            self._warnings.append(f"出力が上限を超えたため切り詰めました: {argv[0]}")
        return result.stdout

    def take_warnings(self) -> list[str]:
        warnings, self._warnings = self._warnings, []
        return warnings

    # ------------------------------------------------------------ Capability

    async def detect_capabilities(self) -> Capabilities:
        version = await self._run(["sinfo", "--version"])
        if not version.ok:
            self._capabilities = Capabilities(notes=(version.error_message(),))
            return self._capabilities
        self._use_json = await self._probe_json()
        self._capabilities = Capabilities(
            slurm_available=True,
            slurm_version=version.stdout.strip() or None,
            squeue_json=self._use_json,
            sacct=self._which("sacct") is not None,
            sstat=self._which("sstat") is not None,
            spart=self._which("spart") is not None,
            module=await self._probe_module(),
            pbs_wrappers=tuple(c for c in PBS_COMMANDS if self._which(c)),
            notes=() if self._use_json else ("squeue --json が使えないためテキスト形式で取得",),
        )
        return self._capabilities

    async def _probe_json(self) -> bool:
        result = await self._run(["squeue", "--json", "--me"])
        if not result.ok:
            return False
        try:
            p.parse_squeue_json(result.stdout)
        except p.ParseError:
            return False
        return True

    async def _probe_module(self) -> bool:
        result = await self._run(["bash", "-lc", "type -t module"], timeout=5.0)
        return result.ok and result.stdout.strip() in {"function", "file", "alias"}

    @property
    def capabilities(self) -> Capabilities:
        return self._capabilities

    # ------------------------------------------------------------ 読み取り

    async def get_jobs(self) -> list[Job]:
        if self._use_json:
            jobs = await self._get_jobs_json()
            if jobs is not None:
                return jobs
        text = await self._run_ok(["squeue", "-h", "-a", "-o", p.SQUEUE_FORMAT])
        return p.parse_squeue_text(text, self._warnings)

    async def _get_jobs_json(self) -> list[Job] | None:
        """JSON で取得する。解析できなければ原因付きで警告し、以後テキスト形式に切り替える。"""
        result = await self._run(["squeue", "--json"], timeout=JSON_TIMEOUT)
        if not result.ok:
            raise AdapterError(result.error_message())
        try:
            return p.parse_squeue_json(result.stdout)
        except p.ParseError as exc:
            self._warnings.append(json_fallback_message(result, exc))
            self._use_json = False
            return None

    async def get_nodes(self) -> list[Node]:
        return p.parse_scontrol_nodes(await self._run_ok(["scontrol", "show", "node", "-o"]))

    async def get_partitions(self) -> list[Partition]:
        text = await self._run_ok(["scontrol", "show", "partition", "-o"])
        partitions = p.parse_scontrol_partitions(text)
        if self._capabilities.spart:
            partitions = merge_spart_limits(partitions, await self.get_spart())
        return partitions

    async def get_job_detail(self, job_id: str) -> Job | None:
        if not is_job_id(job_id):
            raise AdapterError(f"ジョブIDが不正です: {job_id!r}")
        result = await self._run(["scontrol", "show", "job", "-o", job_id])
        if not result.ok:
            return None
        jobs = p.parse_scontrol_jobs(result.stdout)
        return jobs[0] if jobs else None

    async def get_history(self, days: int, max_records: int) -> list[HistoryRecord]:
        argv = [
            "sacct", "-n", "-P", f"--delimiter={p.FIELD_SEP}", "-S", f"now-{int(days)}days",
            "-u", self.current_user, f"--format={','.join(p.SACCT_FIELDS)}",
        ]
        text = await self._run_ok(argv, timeout=SACCT_TIMEOUT)
        records = p.parse_sacct(text, self._warnings)
        records.sort(key=lambda r: _job_sort_key(r.job_id), reverse=True)
        return records[:max_records]

    async def get_spart(self) -> SpartTable | None:
        if not self._capabilities.spart:
            return None
        result = await self._run(["spart"], timeout=SPART_TIMEOUT)
        return parse_spart(result.stdout) if result.ok else None

    async def get_start_estimates(self) -> dict[str, object]:
        result = await self._run(["squeue", "--start", "-h", "-o", f"%i{p.FIELD_SEP}%S"])
        return dict(p.parse_squeue_start(result.stdout)) if result.ok else {}

    async def get_sstat(self, job_id: str) -> CommandResult:
        return await self.run_readonly_tool("sstat", (job_id,))

    async def run_readonly_tool(self, name: str, args: tuple[str, ...] = ()) -> CommandResult:
        argv = build_tool_argv(name, args)
        return await self._run(argv, timeout=15.0)

    # ------------------------------------------------------------ 書き込み

    async def submit_job(self, script_path: str, test_only: bool = False) -> CommandResult:
        argv = ["sbatch", "--parsable"] + (["--test-only"] if test_only else []) + [script_path]
        return await self._run(argv, timeout=SUBMIT_TIMEOUT, cwd=os.path.dirname(script_path))

    async def cancel_job(self, job_id: str) -> CommandResult:
        if not is_job_id(job_id):
            raise AdapterError(f"ジョブIDが不正です: {job_id!r}")
        return await self._run(["scancel", job_id], timeout=10.0)


def _job_sort_key(job_id: str) -> tuple[int, str]:
    head = job_id.split("_", 1)[0]
    return (int(head) if head.isdigit() else -1, job_id)
