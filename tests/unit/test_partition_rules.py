from hakusan_tui.adapters.classify import node_kind, partition_kind
from hakusan_tui.adapters.hakusan import merge_spart_limits, parse_spart
from hakusan_tui.adapters.slurm_parsers import parse_scontrol_partitions
from hakusan_tui.models import Node, Partition
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


def _part(name, nodes=(), tres=None):
    return Partition(name, True, None, len(nodes), None, node_names=tuple(nodes), tres=tres or {})


def test_partition_kind_falls_back_to_name_without_node_info():
    assert partition_kind(_part("GPU-1A")) == "GPU"
    assert partition_kind(_part("GPU-VM")) == "VM"
    assert partition_kind(_part("DEF")) == "CPU"


def test_partition_kind_uses_node_gres_regardless_of_name():
    nodes = [Node("g1", "IDLE", ("a100q",), gres_raw="gpu:a100:4"),
             Node("c1", "IDLE", ("short",), cpus_total=64)]
    assert partition_kind(_part("a100q", ["g1"]), nodes) == "GPU"
    assert partition_kind(_part("short", ["c1"]), nodes) == "CPU"


def test_partition_kind_uses_tres_and_virtual_gpu():
    assert partition_kind(_part("big", tres={"cpu": "8", "gres/gpu": "4"})) == "GPU"
    vm = [Node("v1", "IDLE", ("cloud",), gres_raw="gpu:h100_1_4:4")]
    assert partition_kind(_part("cloud", ["v1"]), vm) == "VM"


def test_node_kind():
    assert node_kind(Node("g", "IDLE", ("GPU-1",), gres_raw="gpu:a40:2")) == "GPU"
    assert node_kind(Node("g", "IDLE", ("batch",), gres_raw="gpu:v100:0")) == "CPU"
    assert node_kind(Node("v", "IDLE", ("x",), gres_raw="gpu:h100_1_4:4")) == "VM"
    assert node_kind(Node("c", "IDLE", ("DEF",))) == "CPU"
    assert node_kind(Node("x", "IDLE", ())) == "不明"
