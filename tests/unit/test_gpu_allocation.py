from hakusan_tui.adapters import gpu
from hakusan_tui.adapters.slurm_parsers import parse_scontrol_nodes
from hakusan_tui.models import Node
from tests.conftest import fixture_text


def node(name="n1", gres="gpu:a40:2", alloc=None, partitions=("GPU-1",), used=None):
    return Node(name=name, state_raw="MIXED", partitions=partitions, gres_raw=gres,
                gres_used_raw=used, alloc_tres=alloc)


def test_parse_gres_variants():
    assert gpu.parse_gres("gpu:a40:2(S:0-1)") == [gpu.GresEntry("gpu", "a40", 2)]
    assert gpu.parse_gres("gpu:2") == [gpu.GresEntry("gpu", None, 2)]
    entries = gpu.parse_gres("gpu:a100:1,gpu:3g.20gb:2(IDX:0,1)")
    assert [e.gpu_type for e in entries] == ["a100", "3g.20gb"]
    assert gpu.parse_gres(None) == []


def test_physical_allocation_from_alloc_tres():
    [a] = gpu.node_gpu_allocations(node(alloc={"cpu": "4", "gres/gpu": "1"}))
    assert (a.total, a.allocated, a.free, a.resource_unit) == (2, 1, 1, "physical_gpu")


def test_empty_alloc_tres_means_zero_allocated():
    [a] = gpu.node_gpu_allocations(node(alloc={}))
    assert (a.allocated, a.free) == (0, 2)


def test_missing_alloc_tres_is_unknown_not_zero():
    [a] = gpu.node_gpu_allocations(node(alloc=None))
    assert a.allocated is None
    assert a.free is None


def test_gres_used_preferred():
    [a] = gpu.node_gpu_allocations(node(used="gpu:a40:2(IDX:0-1)", alloc=None))
    assert (a.allocated, a.free) == (2, 0)


def test_multiple_types_without_per_type_alloc_are_unknown():
    allocs = gpu.node_gpu_allocations(
        node(gres="gpu:a100:1,gpu:3g.20gb:2", alloc={"gres/gpu": "2"})
    )
    assert all(a.allocated is None for a in allocs)
    assert {a.resource_unit for a in allocs} == {"physical_gpu", "mig_instance"}


def test_typed_alloc_used_when_present():
    allocs = gpu.node_gpu_allocations(
        node(gres="gpu:a100:1,gpu:3g.20gb:2",
             alloc={"gres/gpu": "3", "gres/gpu:a100": "1", "gres/gpu:3g.20gb": "2"})
    )
    assert [a.allocated for a in allocs] == [1, 2]


def test_node_in_multiple_partitions_counted_once():
    n = node(partitions=("GPU-1", "GPU-S", "GPU-L"), alloc={})
    summary = gpu.summarize(gpu.gpu_allocations([n, n]))
    assert summary[0].total == 2
    assert summary[0].node_count == 1


def test_fraction_and_mig_not_added_to_physical():
    nodes = [
        node("spcc-a100g01", "gpu:a100:2", {}),
        node("vm-h100q01", "gpu:h100_1_4:1", {"gres/gpu": "1"}),
        node("mig01", "gpu:a100_3g.20gb:7", {}),
    ]
    summary = {(s.group, s.resource_unit): s for s in gpu.summarize(gpu.gpu_allocations(nodes))}
    assert summary[("A100", "physical_gpu")].total == 2
    assert summary[("H100 VM", "virtual_fraction")].total == 1
    assert summary[("A100", "mig_instance")].total == 7


def test_summary_unknown_propagates():
    nodes = [node("a", alloc={}), node("b", alloc=None)]
    [s] = gpu.summarize(gpu.gpu_allocations(nodes))
    assert s.total == 4
    assert s.allocated is None and s.free is None


def test_real_fixture():
    nodes = parse_scontrol_nodes(fixture_text("scontrol_nodes.txt"))
    [s] = gpu.summarize(gpu.gpu_allocations(nodes))
    assert (s.group, s.total, s.allocated, s.free) == ("A40", 2, 2, 0)


def test_unknown_type_unit():
    assert gpu.classify_unit(None) == "unknown"
    assert gpu.classify_unit("mystery") == "unknown"
    assert gpu.classify_group(None, "node1", "unknown") == "不明"
