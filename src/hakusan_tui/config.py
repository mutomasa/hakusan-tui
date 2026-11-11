"""TOML 設定（``~/.config/hakusan-tui/config.toml``）。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir


@dataclass(frozen=True)
class UiConfig:
    language: str = "ja"
    theme: str = "dark"
    default_tab: str = "dashboard"


@dataclass(frozen=True)
class RefreshConfig:
    jobs_seconds: float = 15
    nodes_seconds: float = 30
    history_seconds: float = 60


@dataclass(frozen=True)
class SafetyConfig:
    read_only: bool = False
    confirm_cancel: bool = True
    confirm_submit: bool = True


@dataclass(frozen=True)
class HistoryConfig:
    default_days: int = 7
    max_records: int = 500


@dataclass(frozen=True)
class Config:
    ui: UiConfig = field(default_factory=UiConfig)
    refresh: RefreshConfig = field(default_factory=RefreshConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    profile: str = "hakusan"
    jobs_dir: str = "~/slurm_jobs"
    demo: bool = False


def default_config_path() -> Path:
    return Path(user_config_dir("hakusan-tui")) / "config.toml"


def _merge_section(section: Any, values: dict[str, Any]) -> Any:
    known = {f.name for f in fields(section)}
    return replace(section, **{k: v for k, v in values.items() if k in known})


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    if not path.exists():
        return Config()
    data = tomllib.loads(path.read_text("utf-8"))
    config = Config()
    for name in ("ui", "refresh", "safety", "history"):
        if isinstance(data.get(name), dict):
            config = replace(config, **{name: _merge_section(getattr(config, name), data[name])})
    cluster = data.get("cluster", {})
    if isinstance(cluster, dict) and isinstance(cluster.get("profile"), str):
        config = replace(config, profile=cluster["profile"])
    return config
