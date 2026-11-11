"""スナップショットキャッシュ。

- 同じキーの取得を同時に複数走らせない（単一フライト）。
- TTL 内はキャッシュを返す。手動更新にも短いクールダウンを設ける。
- 失敗時は直前の成功値を残し、エラーと最終成功時刻を保持する。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")

MANUAL_COOLDOWN_SECONDS = 3.0


@dataclass
class Snapshot(Generic[T]):
    value: T | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    fetched_monotonic: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        return self.last_error is not None and self.value is not None

    def age(self, now: float | None = None) -> float | None:
        if self.fetched_monotonic is None:
            return None
        return (now if now is not None else time.monotonic()) - self.fetched_monotonic


class SnapshotStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._snapshots: dict[str, Snapshot[Any]] = {}
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    def get(self, key: str) -> Snapshot[Any]:
        return self._snapshots.setdefault(key, Snapshot())

    def _is_fresh(self, snap: Snapshot[Any], ttl: float, force: bool) -> bool:
        age = snap.age(self._clock())
        if age is None:
            return False
        if force:
            return age < MANUAL_COOLDOWN_SECONDS
        return snap.last_error is None and age < ttl

    async def fetch(
        self, key: str, loader: Callable[[], Awaitable[T]], ttl: float, force: bool = False
    ) -> Snapshot[T]:
        snap = self.get(key)
        if self._is_fresh(snap, ttl, force):
            return snap
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(self._load(key, loader))
            self._inflight[key] = task
            task.add_done_callback(lambda _t: self._inflight.pop(key, None))
        await asyncio.shield(task)
        return self.get(key)

    async def _load(self, key: str, loader: Callable[[], Awaitable[Any]]) -> None:
        snap = self.get(key)
        try:
            value = await loader()
        except Exception as exc:  # 個々の取得失敗でアプリを落とさない
            snap.last_error = str(exc) or exc.__class__.__name__
            snap.fetched_monotonic = self._clock()
            return
        snap.value = value
        snap.last_error = None
        snap.last_success = datetime.now()
        snap.fetched_monotonic = self._clock()

    def invalidate(self, key: str) -> None:
        self.get(key).fetched_monotonic = None
