"""安全な非同期コマンド実行。

- 引数は必ず配列で渡す（shell を経由しない）。
- タイムアウトと出力サイズ上限を設ける。
- サイトや利用者の ``SQUEUE_FORMAT`` などの環境変数で出力形式が変わらないよう除去する。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Mapping, Sequence
from typing import Protocol

from hakusan_tui.models import CommandResult

DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_BYTES = 16 * 1024 * 1024

# 出力形式を上書きしてしまう Slurm の環境変数
_FORMAT_OVERRIDES = (
    "SQUEUE_FORMAT", "SQUEUE_FORMAT2", "SINFO_FORMAT", "SACCT_FORMAT", "SQUEUE_SORT",
    "SLURM_TIME_FORMAT", "SQUEUE_ALL", "SQUEUE_USERS", "SQUEUE_PARTITION", "SLURM_CLUSTERS",
)


class CommandRunner(Protocol):
    async def run(
        self, argv: Sequence[str], *, timeout: float = DEFAULT_TIMEOUT, cwd: str | None = None
    ) -> CommandResult: ...


def build_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in _FORMAT_OVERRIDES:
        env.pop(key, None)
    env["SLURM_TIME_FORMAT"] = "standard"
    return env


async def _read_capped(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, bool]:
    """EOF まで読む。``read(n)`` は n バイト揃う前に返るので必ずループする。

    上限を超えた分は保持せずに読み捨てる（パイプ詰まり防止）。
    """
    if stream is None:
        return b"", False
    chunks: list[bytes] = []
    size = 0
    while chunk := await stream.read(65536):
        if size <= limit:
            chunks.append(chunk)
        size += len(chunk)
    data = b"".join(chunks)
    return data[:limit], size > limit


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class AsyncCommandRunner:
    """``asyncio.create_subprocess_exec`` による実装。"""

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES, env: Mapping[str, str] | None = None):
        self._max_bytes = max_bytes
        self._env = build_environment(env)

    async def run(
        self, argv: Sequence[str], *, timeout: float = DEFAULT_TIMEOUT, cwd: str | None = None
    ) -> CommandResult:
        argv = tuple(argv)
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
                cwd=cwd,
            )
        except (FileNotFoundError, PermissionError):
            return CommandResult(argv, None, "", "", 0.0, not_found=True)
        return await self._collect(proc, argv, started, timeout)

    async def _collect(
        self, proc: asyncio.subprocess.Process, argv: tuple[str, ...], started: float,
        timeout: float,
    ) -> CommandResult:
        try:
            (out, out_trunc), (err, err_trunc) = await asyncio.wait_for(
                asyncio.gather(
                    _read_capped(proc.stdout, self._max_bytes),
                    _read_capped(proc.stderr, self._max_bytes),
                ),
                timeout,
            )
            returncode = await asyncio.wait_for(proc.wait(), timeout)
        except TimeoutError:
            await _terminate(proc)
            return CommandResult(argv, None, "", "", time.monotonic() - started, timed_out=True)
        return CommandResult(
            argv, returncode, _decode(out), _decode(err), time.monotonic() - started,
            truncated=out_trunc or err_trunc,
        )


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.kill()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), 2)
