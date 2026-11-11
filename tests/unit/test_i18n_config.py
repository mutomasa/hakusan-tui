from pathlib import Path

from hakusan_tui.config import load_config
from hakusan_tui.i18n import explain_reason, job_state_display, node_state_label


def test_state_display():
    assert job_state_display("PENDING") == "待機中 (PD)"
    assert job_state_display("RUNNING") == "実行中 (R)"
    assert job_state_display("UNKNOWN", "WEIRD") == "不明 (WEIRD)"


def test_reason_explanations():
    assert "資源" in explain_reason("Resources")
    assert "優先度" in explain_reason("Priority")
    assert "依存" in explain_reason("Dependency")
    assert "QOS" in explain_reason("QOSMaxJobsPerUserLimit")
    assert "上限" in explain_reason("AssocMaxJobsLimit")
    assert "未知の理由: Foo" in explain_reason("Foo")


def test_node_state_label():
    assert node_state_label("IDLE") == "空き"
    assert node_state_label("XYZ") == "不明 (XYZ)"


def test_load_config(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[refresh]\njobs_seconds = 20\nunknown = 1\n[safety]\nread_only = true\n'
                    '[cluster]\nprofile = "generic"\n')
    config = load_config(path)
    assert config.refresh.jobs_seconds == 20 and config.safety.read_only
    assert config.profile == "generic"
    assert load_config(tmp_path / "missing.toml").refresh.jobs_seconds == 15
