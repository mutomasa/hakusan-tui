import asyncio
import os
from pathlib import Path

import pytest

from hakusan_tui.adapters.tools import build_tool_argv
from hakusan_tui.models import Job
from hakusan_tui.services.command_runner import AsyncCommandRunner, build_environment
from hakusan_tui.services.interactive import InteractiveRequest, build_salloc_argv
from hakusan_tui.services.jobs import JobActionService
from hakusan_tui.services.logs import read_log_tail, sanitize_terminal_text


def test_sanitize_removes_ansi_and_controls():
    text = "ok\x1b[31mred\x1b[0m\x1b]0;title\x07\x07bell\r\nnext\x00"
    assert sanitize_terminal_text(text) == "okredbell\nnext"


def test_log_tail_limits_size(tmp_path: Path):
    log = tmp_path / "big.out"
    log.write_bytes(b"a" * 5000 + b"END")
    view = read_log_tail(str(log), max_bytes=100)
    assert view.truncated and view.text.endswith("END") and len(view.text) == 100


def test_log_rejects_directory_and_missing(tmp_path: Path):
    link = tmp_path / "link.out"
    os.symlink(tmp_path, link)
    assert read_log_tail(str(link)).error == "通常のファイルではありません"
    assert "まだありません" in (read_log_tail(str(tmp_path / "none.out")).error or "")
    assert read_log_tail(None).error


def test_module_show_name_passed_as_argument_not_concatenated():
    argv = build_tool_argv("module_show", ("gcc/13.2.0",))
    assert argv[-1] == "gcc/13.2.0" and "gcc" not in argv[2]
    with pytest.raises(ValueError):
        build_tool_argv("module_show", ("gcc; rm -rf ~",))
    with pytest.raises(ValueError):
        build_tool_argv("unknown_tool")


def test_salloc_argv_validation():
    argv = build_salloc_argv(InteractiveRequest(partition="GPU-1", gpus="1", time="01:00:00"))
    assert argv == ["salloc", "-p", "GPU-1", "-n", "1", "--gres", "gpu:1", "--time", "01:00:00"]
    with pytest.raises(ValueError):
        build_salloc_argv(InteractiveRequest(partition="GPU-1; id"))


def test_environment_strips_format_overrides():
    env = build_environment({"SQUEUE_FORMAT": "%i", "SACCT_FORMAT": "x", "PATH": "/bin"})
    assert "SQUEUE_FORMAT" not in env and "SACCT_FORMAT" not in env
    assert env["SLURM_TIME_FORMAT"] == "standard" and env["PATH"] == "/bin"


# ------------------------------------------------------------- コマンドランナー


async def test_runner_not_found():
    result = await AsyncCommandRunner().run(["definitely-not-a-command-xyz"])
    assert result.not_found and not result.ok


async def test_runner_timeout():
    result = await AsyncCommandRunner().run(["sleep", "5"], timeout=0.2)
    assert result.timed_out and not result.ok


async def test_runner_truncates_output():
    result = await AsyncCommandRunner(max_bytes=10).run(["python3", "-c", "print('x'*1000)"])
    assert result.ok and result.truncated and len(result.stdout) == 10


async def test_runner_reads_large_output_completely():
    """回帰: StreamReader.read(n) は1チャンクで返るため、以前は約40KBで出力が切れていた。"""
    result = await AsyncCommandRunner().run(
        ["python3", "-c", "import sys; sys.stdout.write('y' * 300000)"]
    )
    assert result.ok and not result.truncated and len(result.stdout) == 300000


async def test_runner_does_not_use_shell(tmp_path: Path):
    marker = tmp_path / "pwned"
    result = await AsyncCommandRunner().run(["echo", f"; touch {marker}"])
    assert result.ok and not marker.exists()


# ------------------------------------------------------------- キャンセルの安全性


class FakeAdapter:
    mode = "slurm"
    executes_commands = True
    current_user = "me"
    hostname = "h"

    def __init__(self, job: Job | None):
        self.job = job
        self.cancelled: list[str] = []

    async def get_job_detail(self, job_id):
        return self.job

    async def cancel_job(self, job_id):
        from tests.conftest import ok

        self.cancelled.append(job_id)
        return ok(["scancel", job_id])


def make_job(user="me", state="RUNNING", job_id="42"):
    return Job(job_id=job_id, user=user, name="n", partition="DEF", state_raw=state,
               state_normalized=state)


async def test_cancel_own_job_executes():
    adapter = FakeAdapter(make_job())
    outcome = await JobActionService(adapter, read_only=False).cancel("42.batch")
    assert outcome.ok and outcome.executed and adapter.cancelled == ["42"]


@pytest.mark.parametrize(
    ("job", "read_only", "job_id"),
    [
        (make_job(user="other"), False, "42"),     # 他人のジョブ
        (make_job(state="COMPLETED"), False, "42"),  # 終了済み
        (None, False, "42"),                        # 見つからない
        (make_job(), True, "42"),                   # 読み取り専用
        (make_job(), False, "42; rm -rf ~"),        # 不正なID
    ],
)
async def test_cancel_refused(job, read_only, job_id):
    adapter = FakeAdapter(job)
    outcome = await JobActionService(adapter, read_only=read_only).cancel(job_id)
    assert not outcome.ok and adapter.cancelled == []


async def test_cancel_refused_in_demo():
    adapter = FakeAdapter(make_job())
    adapter.executes_commands = False
    outcome = await JobActionService(adapter, read_only=False).cancel("42")
    assert not outcome.ok and adapter.cancelled == []


def test_event_loop_policy_sanity():
    assert asyncio.get_event_loop_policy() is not None
