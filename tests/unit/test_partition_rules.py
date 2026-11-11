from hakusan_tui.adapters.hakusan import (
    merge_spart_limits,
    node_kind,
    parse_spart,
    partition_kind,
)
from hakusan_tui.adapters.slurm_parsers import parse_scontrol_partitions
from hakusan_tui.models import Node
from tests.conftest import fixture_text


def test_parse_spart_real_stub():
    table = parse_spart(fixture_text("spart.txt"))
    assert table.parsed
    assert table.headers[0] == "QUEUE PARTITION"
    assert table.rows[0]["QUEUE PARTITION"] == "DEF*"
    assert table.rows[2]["MAX WALLTIME"] == "12:00"


def test_parse_spart_unparseable_keeps_raw():
    raw = "some banner\nunexpected format\nwith ragged columns a b c\n"
    table = parse_spart(raw)
    assert not table.parsed
    assert table.raw == raw


def test_merge_spart_limits_by_name_without_default_marker():
    parts = parse_scontrol_partitions(fixture_text("scontrol_partitions.txt"))
    merged = {p.name: p for p in merge_spart_limits(parts, parse_spart(fixture_text("spart.txt")))}
    assert merged["DEF"].site_limits["MAX WALLTIME"] == "1-00:00"
    assert merged["GPU-S"].site_limits["TOTAL CORES"] == "4"


def test_merge_without_spart_keeps_empty_limits():
    parts = parse_scontrol_partitions(fixture_text("scontrol_partitions.txt"))
    assert all(p.site_limits == {} for p in merge_spart_limits(parts, None))


def test_partition_and_node_kind():
    assert partition_kind("GPU-1A") == "GPU"
    assert partition_kind("GPU-VM") == "VM"
    assert partition_kind("DEF") == "CPU"
    assert node_kind(Node("g", "IDLE", ("GPU-1",), gres_raw="gpu:a40:2")) == "GPU"
    assert node_kind(Node("c", "IDLE", ("DEF",))) == "CPU"
    assert node_kind(Node("x", "IDLE", ())) == "不明"
