"""共通フィクスチャ。Slurm 実機なしで動く偽コマンドランナーを提供する。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from hakusan_tui.models import CommandResult

FIXTURES = Path(__file__).parent / "fixtures" / "slurm-23.11"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text("utf-8")


Responder = Callable[[tuple[str, ...]], CommandResult | None]


def ok(argv: Sequence[str], stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(tuple(argv), 0, stdout, stderr, 0.01)


def fail(argv: Sequence[str], stderr: str = "error", code: int = 1) -> CommandResult:
    return CommandResult(tuple(argv), code, "", stderr, 0.01)


class FakeRunner:
    """argv の先頭一致で応答を返す。呼び出し履歴を記録する。"""

    def __init__(self, routes: dict[tuple[str, ...], Callable[[tuple[str, ...]], CommandResult]]):
        self.routes = routes
        self.calls: list[tuple[str, ...]] = []

    async def run(self, argv: Sequence[str], *, timeout: float = 5.0, cwd: str | None = None):
        argv = tuple(argv)
        self.calls.append(argv)
        for prefix in sorted(self.routes, key=len, reverse=True):
            if argv[: len(prefix)] == prefix:
                return self.routes[prefix](argv)
        return CommandResult(argv, None, "", "", 0.0, not_found=True)

    def called(self, *prefix: str) -> bool:
        return any(c[: len(prefix)] == prefix for c in self.calls)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
