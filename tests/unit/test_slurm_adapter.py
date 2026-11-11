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



def _text_line(job_id: str, user: str, name: str = "job") -> str:
    return FIELD_SEP.join([job_id, user, "DEF", "RUNNING", "1:00", "10:00", "1", "1", "N/A",
                           "lcpcc-001", name])


async def _adapter_with(me_stdout: str, truncated: bool = False, text: str | None = None):
    from hakusan_tui.models import CommandResult

    text = text if text is not None else _text_line("9", "otheruser") + "\n"

    def squeue_json(a):
        if a == ("squeue", "--json", "--me") and not truncated and me_stdout.startswith("{\n"):
            return ok(a, me_stdout)
        return CommandResult(tuple(a), 0, me_stdout, "", 0.1, truncated=truncated)

    adapter, runner = make({
        ("sinfo", "--version"): lambda a: ok(a, "slurm 25.05.5\n"),
        ("squeue", "--json"): squeue_json,
        ("squeue", "-h"): lambda a: ok(a, text),
        ("bash", "-lc"): lambda a: ok(a, "function\n"),
    })
    caps = await adapter.detect_capabilities()
    return adapter, runner, caps


async def test_all_jobs_use_text_and_never_full_json():
    """全ジョブの squeue --json は使わない（HAKUSAN 実機で 16MiB を超えた）。"""
    adapter, runner, _ = await _adapter_with(fixture_text("squeue_me.json"))
    jobs = await adapter.get_jobs()
    assert ("squeue", "--json") not in runner.calls
    assert runner.called("squeue", "-h", "-a", "-o")
    assert runner.called("squeue", "--json", "--me")
    users = {j.user for j in jobs}
    assert {"otheruser", "testuser"} <= users


async def test_own_jobs_replaced_by_json_details():
    text = _text_line("4", "testuser", "train vla|x") + "\n" + _text_line("9", "otheruser") + "\n"
    adapter, _, _ = await _adapter_with(fixture_text("squeue_me.json"), text=text)
    jobs = {j.job_id: j for j in await adapter.get_jobs()}
    assert jobs["4"].requested_tres.get("gres/gpu") == "1"  # JSON 由来の詳細
    assert jobs["4"].stdout_path
    assert jobs["9"].user == "otheruser" and jobs["9"].requested_tres == {}
    assert len([j for j in jobs.values() if j.job_id == "4"]) == 1


async def test_broken_my_json_falls_back_with_cause():
    adapter, runner, caps = await _adapter_with(fixture_text("squeue_me.json"))
    assert caps.squeue_json
    adapter._runner.routes[("squeue", "--json")] = lambda a: ok(a, '{"jobs": [{"name": "a" "b"}]}')
    jobs = await adapter.get_jobs()
    [warning] = adapter.take_warnings()
    assert jobs[0].job_id == "9"
    assert "JSON が不正" in warning and "バイト" in warning
    assert '"a"' not in warning  # 出力内容（他人のジョブ名など）は警告に含めない
    before = len(runner.calls)
    await adapter.get_jobs()
    assert not any(c[:2] == ("squeue", "--json") for c in runner.calls[before:])  # 以後はテキストのみ


async def test_truncated_json_reports_truncation():
    adapter, _, _ = await _adapter_with(fixture_text("squeue_me.json"))
    from hakusan_tui.models import CommandResult

    adapter._runner.routes[("squeue", "--json")] = lambda a: CommandResult(
        tuple(a), 0, '{"jobs": [', "", 0.1, truncated=True)
    await adapter.get_jobs()
    [warning] = adapter.take_warnings()
    assert "切り詰め" in warning


def test_merge_pending_array_job_not_duplicated():
    from hakusan_tui.adapters.slurm import merge_jobs
    from hakusan_tui.models import Job

    def job(i, user="me"):
        return Job(job_id=i, user=user, name="n", partition="DEF", state_raw="PENDING",
                   state_normalized="PENDING")

    merged = merge_jobs([job("123_[1-10]"), job("5", "other")], [job("123"), job("200")])
    assert [j.job_id for j in merged] == ["5", "123", "200"]
