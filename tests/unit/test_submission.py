from pathlib import Path

import pytest

from hakusan_tui.adapters.slurm_parsers import parse_scontrol_nodes, parse_scontrol_partitions
from hakusan_tui.services import submission as sub
from tests.conftest import fixture_text

PARTS = parse_scontrol_partitions(fixture_text("scontrol_partitions.txt"))
NODES = parse_scontrol_nodes(fixture_text("scontrol_nodes.txt"))


def errors(spec):
    return {i.field for i in sub.validate(spec, PARTS, NODES) if i.level == "error"}


def base(**kw):
    return sub.JobSpec(job_name="t1", command="./a.out", **kw)


def test_valid_spec_has_no_errors():
    assert errors(base(partition="DEF", time="01:00:00", mem="1G")) == set()


def test_time_over_partition_limit():
    assert "time" in errors(base(partition="TINY", time="01:00:00"))


def test_invalid_memory_and_numbers():
    assert {"mem", "ntasks", "cpus_per_task"} <= errors(base(mem="32GB!", ntasks="0", cpus_per_task="x"))


def test_gpu_more_than_node_has():
    assert "gpus" in errors(base(partition="GPU-1", gpus="3"))
    assert "gpus" not in errors(base(partition="GPU-1", gpus="2"))


def test_gpu_on_cpu_partition_is_warning():
    issues = sub.validate(base(partition="DEF", gpus="1"), PARTS, NODES)
    assert any(i.field == "gpus" and i.level == "warning" for i in issues)


def test_unknown_partition_is_error():
    assert "partition" in errors(base(partition="NOPE"))


def test_partition_info_missing_is_info_not_guess():
    issues = sub.validate(base(partition="DEF"), None, None)
    assert [i.level for i in issues if i.field == "partition"] == ["info"]


def test_no_partition_uses_cluster_default():
    issues = sub.validate(base(), PARTS, NODES)
    assert any("クラスタ既定" in i.message for i in issues)
    assert "--partition" not in sub.render_script(base())


@pytest.mark.parametrize("field", ["job_name", "partition", "output", "mem", "mail_user"])
def test_header_injection_rejected(field):
    spec = base(**{field: "x\n#SBATCH --uid=0"}) if field != "job_name" else sub.JobSpec(
        job_name="x\n#SBATCH --uid=0", command="true")
    assert field in errors(spec)


def test_memory_over_node():
    assert "mem" in errors(base(partition="DEF", mem="10G"))


def test_mail_validation():
    assert "mail_type" in errors(base(mail_type="SOMETIMES"))
    assert "mail_user" in errors(base(mail_type="END", mail_user="not-an-email"))
    assert not errors(base(mail_type="END,FAIL", mail_user="a@example.ac.jp"))


def test_module_name_validation():
    assert "modules" in errors(base(modules=("gcc; rm -rf ~",)))


def test_render_script_contents():
    spec = base(partition="GPU-1", gpus="1", gpu_type="a40", time="02:00:00",
                modules=("cuda/12.4",), mail_type="end", mail_user="a@example.ac.jp")
    script = sub.render_script(spec)
    assert script.startswith("#!/bin/bash\n")
    assert "#SBATCH --gres=gpu:a40:1" in script
    assert "#SBATCH --mail-type=END" in script
    assert "module load cuda/12.4" in script
    assert 'cd "$SLURM_SUBMIT_DIR"' in script
    assert script.rstrip().endswith("./a.out")


def test_staging_template():
    spec = sub.apply_template("staging", sub.JobSpec(job_name="st"))
    script = sub.render_script(spec)
    assert "trap copy_back EXIT" in script
    assert 'cd "$JOBDIR"' in script
    assert "input.dat" in script and "result.dat" in script
    assert "JOBDIR が利用できません" in script


def test_staging_rejects_absolute_and_parent_paths():
    assert "staging" in errors(base(use_staging=True, stage_in=("/etc/passwd",)))
    assert "staging" in errors(base(use_staging=True, stage_out=("../x",)))


def test_template_switch_resets_fields_but_keeps_name_and_partition():
    spec = sub.apply_template("python_ai", sub.JobSpec(job_name="keep", partition="GPU-1"))
    assert spec.gpus == "1"
    again = sub.apply_template("cpu_single", spec)
    assert again.gpus == "" and again.job_name == "keep" and again.partition == "GPU-1"


def test_save_refuses_overwrite(tmp_path: Path):
    spec = base()
    path = sub.default_script_path(spec, str(tmp_path))
    sub.save_script(spec, path)
    with pytest.raises(FileExistsError):
        sub.save_script(spec, path)
    sub.save_script(sub.JobSpec(job_name="t1", command="echo new"), path, overwrite=True)
    assert "echo new" in path.read_text()


def test_sbatch_preview_quotes_path(tmp_path: Path):
    path = tmp_path / "my dir" / "job.sh"
    assert sub.sbatch_preview(path) == f"cd '{path.parent}' && sbatch --parsable job.sh"
