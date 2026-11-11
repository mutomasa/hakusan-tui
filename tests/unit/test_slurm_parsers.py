from datetime import datetime

import pytest

from hakusan_tui.adapters import slurm_parsers as p
from tests.conftest import fixture_text


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("0:14", 14), ("05:00", 300), ("12:00:00", 43200), ("1-00:00:00", 86400),
        ("2-03", 2 * 86400 + 3 * 3600), ("30", 1800), ("UNLIMITED", None), ("N/A", None),
        ("INVALID", None), ("", None), (None, None), ("abc", None),
    ],
)
def test_parse_duration(text, seconds):
    assert p.parse_duration(text) == seconds


def test_format_duration_roundtrip():
    assert p.format_duration(90061) == "1-01:01:01"
    assert p.format_duration(59) == "00:00:59"


@pytest.mark.parametrize(
    ("text", "mib"),
    [("3232K", 3232 / 1024), ("250M", 250.0), ("2G", 2048.0), ("1T", 1024.0 * 1024), ("100", 100.0),
     ("", None), ("x", None)],
)
def test_parse_memory(text, mib):
    assert p.parse_memory_mib(text) == mib


def test_normalize_state():
    assert p.normalize_state("CANCELLED by 3000") == "CANCELLED"
    assert p.normalize_state("RUNNING+COMPLETING") == "RUNNING"
    assert p.normalize_state("OOM") == "OUT_OF_MEMORY"
    assert p.normalize_state("WEIRD_NEW_STATE") == "UNKNOWN"
    assert p.normalize_state("") == "UNKNOWN"


def test_parse_tres():
    assert p.parse_tres("cpu=1,mem=250M,gres/gpu=1") == {"cpu": "1", "mem": "250M", "gres/gpu": "1"}
    assert p.parse_tres("(null)") == {}
    assert p.parse_tres("") == {}


def test_key_values_with_spaces_in_values():
    kv = p.parse_key_values(
        "NodeName=n1 OS=Linux 7.0 #38 SMP Mon Sep 14 Reason=Not responding [slurm@2026] CfgTRES=cpu=4,mem=2000M"
    )
    assert kv["OS"] == "Linux 7.0 #38 SMP Mon Sep 14"
    assert kv["Reason"] == "Not responding [slurm@2026]"
    assert kv["CfgTRES"] == "cpu=4,mem=2000M"


def test_split_job_reason():
    assert p.split_job_reason("(Resources)") == (None, "Resources")
    assert p.split_job_reason("lcpcc-001") == ("lcpcc-001", None)


def test_expand_hostlist():
    assert p.expand_hostlist("spcc-a40g[01-03,05]") == (
        "spcc-a40g01", "spcc-a40g02", "spcc-a40g03", "spcc-a40g05"
    )
    assert p.expand_hostlist("a,b[1-2]") == ("a", "b1", "b2")
    assert p.expand_hostlist("(null)") == ()


# ------------------------------------------------------------- 実機フィクスチャ


def test_squeue_json_real_fixture():
    jobs = p.parse_squeue_json(fixture_text("squeue.json"), now=datetime(2026, 11, 11, 10, 40))
    by_name = {j.name: j for j in jobs}
    pending = by_name["train vla|x"]  # ジョブ名にパイプを含む
    assert pending.state_normalized == "PENDING"
    assert pending.reason == "Resources"
    assert pending.requested_tres["gres/gpu"] == "1"
    assert pending.time_limit_seconds == 12 * 3600
    assert pending.start_time is None  # 待機中の推定開始を開始時刻として扱わない
    running = by_name["other_big"]
    assert running.user == "otheruser"
    assert running.node_list == "spcc-a40g01"
    assert running.allocated_tres["gres/gpu"] == "2"


def test_squeue_json_invalid():
    with pytest.raises(p.ParseError):
        p.parse_squeue_json("not json")
    with pytest.raises(p.ParseError):
        p.parse_squeue_json('{"meta": {}}')


def test_json_version():
    assert p.json_slurm_version(fixture_text("squeue.json")) == "23.11.4"


def test_squeue_text_with_unit_separator_keeps_pipe_in_name():
    sep = p.FIELD_SEP
    line = sep.join(["4", "testuser", "GPU-1", "PENDING", "0:00", "12:00:00", "1", "1",
                     "gres/gpu:1", "(Resources)", "train vla|x"])
    jobs = p.parse_squeue_text(line + "\n")
    assert jobs[0].name == "train vla|x"
    assert jobs[0].reason == "Resources"
    assert jobs[0].node_list is None


def test_squeue_text_broken_line_is_skipped_with_warning():
    warnings: list[str] = []
    jobs = p.parse_squeue_text("garbage line without separators\n", warnings)
    assert jobs == []
    assert warnings and "スキップ" in warnings[0]


def test_pipe_delimited_squeue_is_ambiguous_in_real_output():
    """実機で | 区切りにするとジョブ名の | で列数が変わることの記録（だから 0x1f を使う）。"""
    lines = fixture_text("squeue_text.txt").splitlines()
    counts = {line.count("|") for line in lines}
    assert len(counts) == 2


def test_scontrol_nodes_real_fixture():
    nodes = {n.name: n for n in p.parse_scontrol_nodes(fixture_text("scontrol_nodes.txt"))}
    gpu = nodes["spcc-a40g01"]
    assert gpu.gres_raw == "gpu:a40:2"
    assert gpu.partitions == ("GPU-1", "GPU-S")
    assert gpu.alloc_tres == {"cpu": "1", "mem": "250M", "gres/gpu": "2"}
    assert gpu.base_state == "MIXED"
    assert nodes["lcpcc-001"].gres_raw is None


def test_scontrol_partitions_real_fixture():
    parts = {x.name: x for x in p.parse_scontrol_partitions(fixture_text("scontrol_partitions.txt"))}
    assert parts["DEF"].is_default is True
    assert parts["TINY"].max_time_seconds == 1800
    assert parts["GPU-1"].node_names == ("spcc-a40g01",)
    assert parts["GPU-1"].tres["gres/gpu"] == "2"
    assert parts["GPU-1"].available is True


def test_scontrol_jobs_real_fixture():
    jobs = {j.job_id: j for j in p.parse_scontrol_jobs(fixture_text("scontrol_jobs.txt"))}
    job = jobs["4"]
    assert job.name == "train vla|x"
    assert job.user == "testuser"
    assert job.reason == "Resources"
    assert job.stdout_path and job.stdout_path.endswith(".out")


def test_sacct_real_fixture_groups_steps():
    records = {r.job_id: r for r in p.parse_sacct(fixture_text("sacct.txt"))}
    first = records["1"]
    assert [s.step_id for s in first.steps] == ["1.batch"]
    assert first.max_rss_mib == pytest.approx(3232 / 1024)
    assert first.alloc_tres["gres/gpu"] == "1"
    # MaxRSS がステップに無いジョブは None（0 ではない）
    assert records["2"].max_rss_mib is None
    assert records["4"].name == "train vla|x"  # 名前の | を保持
    assert records["5"].alloc_cpus == 2


def test_sacct_name_last_protects_delimiter():
    sep = p.FIELD_SEP
    row = sep.join(["7", "u", "DEF", "COMPLETED", "0:0", "00:00:01", "1", "cpu=1", "cpu=1", "",
                    "2026-11-11T10:00:00", "2026-11-11T10:00:01", "2026-11-11T09:59:00", "/home/u",
                    f"name{sep}with{sep}sep"])
    records = p.parse_sacct(row)
    assert records[0].name == f"name{sep}with{sep}sep"


def test_squeue_start():
    est = p.parse_squeue_start(fixture_text("squeue_start.txt"))
    assert est["4"] == datetime(2026, 11, 11, 22, 39, 32)


def test_sbatch_parsable():
    assert p.parse_sbatch_parsable("123\n") == "123"
    assert p.parse_sbatch_parsable("123;hakusan\n") == "123"
    assert p.parse_sbatch_parsable("Submitted batch job 5") is None
    assert p.parse_sbatch_parsable("") is None


def test_top_level_job_id():
    assert p.top_level_job_id("123.batch") == "123"
    assert p.top_level_job_id("123_4") == "123_4"
    assert p.top_level_job_id("55+1") == "55"
