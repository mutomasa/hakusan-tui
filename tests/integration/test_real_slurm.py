"""Docker 上の実 Slurm（docker/compose.yml）に対する結合テスト。

実行: docker compose -f docker/compose.yml exec ctl /work/docker/run-integration.sh
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path

import pytest

from hakusan_tui.adapters.gpu import gpu_allocations
from hakusan_tui.adapters.slurm import SlurmAdapter
from hakusan_tui.adapters.slurm_parsers import parse_sbatch_parsable
from hakusan_tui.services import submission as sub
from hakusan_tui.services.jobs import JobActionService
from hakusan_tui.services.logs import read_log_tail

pytestmark = [
    pytest.mark.slurm,
    pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm がありません"),
]


@pytest.fixture
async def adapter() -> SlurmAdapter:
    a = SlurmAdapter()
    await a.detect_capabilities()
    return a


@pytest.fixture
def job_dir() -> Path:
    # 計算ノードと共有される /home 配下に置く（/tmp はノード間で共有されない）
    path = Path.home() / "it_jobs" / uuid.uuid4().hex[:8]
    path.mkdir(parents=True)
    return path


async def wait_for(predicate, timeout: float = 60, interval: float = 1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        value = await predicate()
        if value:
            return value
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("タイムアウト")
        await asyncio.sleep(interval)


async def submit(adapter: SlurmAdapter, job_dir: Path, **kw) -> str:
    spec = sub.JobSpec(job_name=f"it_{job_dir.name}", output="%x-%j.out", error="%x-%j.err", **kw)
    issues = sub.validate(spec, await adapter.get_partitions(), await adapter.get_nodes())
    assert not sub.has_errors(issues), issues
    path = sub.save_script(spec, job_dir / "job.sh")
    result = await adapter.submit_job(str(path))
    assert result.ok, result.error_message()
    job_id = parse_sbatch_parsable(result.stdout)
    assert job_id
    return job_id


async def test_capabilities(adapter):
    caps = adapter.capabilities
    assert caps.slurm_available and caps.squeue_json and caps.sacct and caps.spart
    assert caps.module
    assert "23.11" in (caps.slurm_version or "")


async def test_nodes_partitions_and_spart(adapter):
    nodes = {n.name: n for n in await adapter.get_nodes()}
    assert {"lcpcc-001", "spcc-a40g01"} <= set(nodes)
    [gpu] = gpu_allocations([nodes["spcc-a40g01"]])
    assert gpu.total == 2 and gpu.gpu_type == "a40" and gpu.allocated is not None
    parts = {p.name: p for p in await adapter.get_partitions()}
    assert parts["DEF"].is_default and parts["TINY"].max_time_seconds == 1800
    assert parts["GPU-1"].site_limits  # spart の値が付与されている


async def test_lifecycle_submit_queue_log_cancel_history(adapter, job_dir):
    job_id = await submit(adapter, job_dir, partition="DEF", time="00:10:00",
                          command='echo "hello-from-$(hostname)"\nsleep 120')

    async def running():
        jobs = {j.job_id: j for j in await adapter.get_jobs()}
        job = jobs.get(job_id)
        return job if job is not None and job.is_running else None

    job = await wait_for(running)
    assert job.user == os.environ.get("USER", job.user) and job.node_list == "lcpcc-001"
    detail = await adapter.get_job_detail(job_id)
    assert detail is not None and detail.stdout_path

    async def log_ready():
        view = read_log_tail(detail.stdout_path)
        return view if "hello-from-lcpcc-001" in view.text else None

    await wait_for(log_ready, timeout=30)

    outcome = await JobActionService(adapter, read_only=False).cancel(job_id)
    assert outcome.ok and outcome.executed

    async def cancelled():
        d = await adapter.get_job_detail(job_id)
        return d is None or d.state_normalized == "CANCELLED"

    await wait_for(cancelled, timeout=30)

    async def in_history():
        records = {r.job_id: r for r in await adapter.get_history(1, 500)}
        record = records.get(job_id)
        return record if record and record.state_normalized == "CANCELLED" else None

    record = await wait_for(in_history, timeout=60, interval=2)
    assert record.partition == "DEF"


async def test_gpu_job_allocation_is_visible(adapter, job_dir):
    job_id = await submit(adapter, job_dir, partition="GPU-1", gpus="1", gpu_type="a40",
                          time="00:05:00", command='echo "GPU=$CUDA_VISIBLE_DEVICES"\nsleep 60')

    async def allocated():
        nodes = [n for n in await adapter.get_nodes() if n.name == "spcc-a40g01"]
        [a] = gpu_allocations(nodes)
        return a if a.allocated and a.allocated >= 1 else None

    alloc = await wait_for(allocated)
    assert alloc.free is not None and alloc.free == alloc.total - alloc.allocated
    assert (await JobActionService(adapter, read_only=False).cancel(job_id)).ok


async def test_cannot_cancel_other_users_job(adapter):
    other = os.environ.get("OTHER_JOB_ID")
    if not other:
        pytest.skip("OTHER_JOB_ID 未設定（run-integration.sh から実行してください）")
    outcome = await JobActionService(adapter, read_only=False).cancel(other)
    assert not outcome.ok and not outcome.executed
    detail = await adapter.get_job_detail(other)
    assert detail is not None and detail.state_normalized in {"PENDING", "RUNNING"}


async def test_sbatch_error_is_reported(adapter, job_dir):
    script = job_dir / "bad.sh"
    script.write_text("#!/bin/bash\n#SBATCH --partition=NO_SUCH_PARTITION\ntrue\n")
    result = await adapter.submit_job(str(script))
    assert not result.ok and "partition" in result.error_message().lower()


async def test_sbatch_test_only(adapter, job_dir):
    path = sub.save_script(sub.JobSpec(job_name="testonly", command="true"), job_dir / "t.sh")
    result = await adapter.submit_job(str(path), test_only=True)
    assert result.ok or "to start" in result.stderr


async def test_text_fallback_on_real_cluster(adapter):
    adapter._use_json = False  # 古い Slurm を想定
    jobs = await adapter.get_jobs()
    assert isinstance(jobs, list)
    assert not adapter.take_warnings()


async def test_module_tools(adapter):
    result = await adapter.run_readonly_tool("module_avail")
    assert result.ok and "gcc/13.2.0" in result.stdout
    show = await adapter.run_readonly_tool("module_show", ("cuda/12.4",))
    assert "CUDA_HOME" in show.stdout


async def test_tui_against_real_slurm():
    from textual.widgets import DataTable

    from hakusan_tui.app import HakusanApp
    from hakusan_tui.config import Config

    app = HakusanApp(Config(), SlurmAdapter())
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(3)
        app.action_switch_tab("nodes")
        await pilot.pause(0.5)
        assert app.query_one("#nodes-table", DataTable).row_count == 2
        assert "接続: 正常" in str(app.query_one("#topbar").render())


async def test_staging_copy_back_with_jobdir(adapter, job_dir):
    """Prolog が $JOBDIR を作るテストクラスタで、input→$JOBDIR→output の copy-back を確認。"""
    (job_dir / "input.dat").write_text("3\n4\n")
    spec = sub.apply_template("staging", sub.JobSpec(job_name=f"st_{job_dir.name}"))
    spec = sub.replace(spec, partition="DEF", time="00:05:00",
                       command='pwd > where.txt\nawk "{s+=\\$1} END {print s}" input.dat > result.dat',
                       stage_out=("result.dat", "where.txt"))
    path = sub.save_script(spec, job_dir / "job.sh")
    result = await adapter.submit_job(str(path))
    job_id = parse_sbatch_parsable(result.stdout)
    assert job_id, result.error_message()

    async def done():
        d = await adapter.get_job_detail(job_id)
        return d if d is not None and not d.is_active else None

    detail = await wait_for(done, timeout=60)
    assert detail.state_normalized == "COMPLETED", read_log_tail(str(job_dir / f"st_{job_dir.name}-{job_id}.err")).text
    assert (job_dir / "result.dat").read_text().strip() == "7"
    assert (job_dir / "where.txt").read_text().strip() == f"/JOBs/{job_id}"


def test_salloc_interactive_session_returns():
    """salloc で割当→シェル→exit で戻ること（標準入力からコマンドを流して疑似的に操作）。"""
    import subprocess
    import sys

    code = (
        "from hakusan_tui.services.interactive import run_interactive, build_salloc_argv, "
        "InteractiveRequest; import sys; "
        "sys.exit(run_interactive(build_salloc_argv(InteractiveRequest(partition='DEF', "
        "time='00:02:00'))))"
    )
    proc = subprocess.run([sys.executable, "-c", code], input="srun hostname\nexit\n",
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "lcpcc-001" in proc.stdout
    assert "Granted job allocation" in proc.stderr
