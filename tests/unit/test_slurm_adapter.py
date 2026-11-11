from hakusan_tui.adapters.slurm import SlurmAdapter
from hakusan_tui.adapters.slurm_parsers import FIELD_SEP
from tests.conftest import FakeRunner, fail, fixture_text, ok


def which_all(name):
    return f"/usr/bin/{name}" if name in {"sacct", "sstat", "spart"} else None


def make(routes):
    runner = FakeRunner(routes)
    return SlurmAdapter(runner=runner, user="testuser", which=which_all), runner


async def test_capabilities_with_json():
    adapter, _ = make({
        ("sinfo", "--version"): lambda a: ok(a, "slurm-wlm 23.11.4\n"),
        ("squeue", "--json"): lambda a: ok(a, fixture_text("squeue_me.json")),
        ("bash", "-lc"): lambda a: ok(a, "function\n"),
    })
    caps = await adapter.detect_capabilities()
    assert caps.slurm_available and caps.squeue_json and caps.spart and caps.module
    assert caps.slurm_version == "slurm-wlm 23.11.4"
    assert caps.pbs_wrappers == ()


async def test_no_slurm():
    adapter, _ = make({})
    caps = await adapter.detect_capabilities()
    assert not caps.slurm_available and "見つかりません" in caps.notes[0]


async def test_json_unavailable_falls_back_to_text():
    line = FIELD_SEP.join(["9", "testuser", "DEF", "RUNNING", "1:00", "10:00", "1", "1", "N/A",
                           "lcpcc-001", "job|name"])
    adapter, runner = make({
        ("sinfo", "--version"): lambda a: ok(a, "slurm 20.02\n"),
        ("squeue", "--json"): lambda a: fail(a, "squeue: unrecognized option '--json'"),
        ("squeue", "-h"): lambda a: ok(a, line + "\n"),
        ("bash", "-lc"): lambda a: fail(a),
    })
    caps = await adapter.detect_capabilities()
    assert not caps.squeue_json
    jobs = await adapter.get_jobs()
    assert jobs[0].name == "job|name" and jobs[0].node_list == "lcpcc-001"
    assert runner.called("squeue", "-h", "-a", "-o")


async def test_history_uses_bounded_period_and_user():
    adapter, runner = make({("sacct",): lambda a: ok(a, fixture_text("sacct.txt"))})
    records = await adapter.get_history(days=7, max_records=2)
    argv = runner.calls[0]
    assert "-S" in argv and argv[argv.index("-S") + 1] == "now-7days"
    assert argv[argv.index("-u") + 1] == "testuser"
    assert len(records) == 2 and records[0].job_id == "6"


async def test_get_job_detail_rejects_bad_id():
    adapter, runner = make({})
    try:
        await adapter.get_job_detail("1; rm")
    except Exception as exc:
        assert "不正" in str(exc)
    assert runner.calls == []


async def test_submit_runs_in_script_directory(tmp_path):
    seen = {}

    class Runner(FakeRunner):
        async def run(self, argv, *, timeout=5.0, cwd=None):
            seen["cwd"] = cwd
            return await super().run(argv, timeout=timeout, cwd=cwd)

    runner = Runner({("sbatch",): lambda a: ok(a, "77\n")})
    adapter = SlurmAdapter(runner=runner, user="u", which=which_all)
    script = tmp_path / "job.sh"
    result = await adapter.submit_job(str(script))
    assert result.stdout == "77\n" and seen["cwd"] == str(tmp_path)
    assert runner.calls[0] == ("sbatch", "--parsable", str(script))
