import asyncio

from hakusan_tui.services.refresh import SnapshotStore


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


async def test_single_flight():
    store = SnapshotStore()
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return calls

    a, b = await asyncio.gather(store.fetch("k", loader, 10), store.fetch("k", loader, 10))
    assert calls == 1 and a.value == b.value == 1


async def test_ttl_and_force_cooldown():
    clock = Clock()
    store = SnapshotStore(clock)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return calls

    await store.fetch("k", loader, ttl=15)
    clock.now = 5
    assert (await store.fetch("k", loader, ttl=15)).value == 1  # TTL 内はキャッシュ
    clock.now = 6
    await store.fetch("k", loader, ttl=15, force=True)
    assert calls == 2  # 手動更新（クールダウン 3 秒を超えた）
    clock.now = 7
    await store.fetch("k", loader, ttl=15, force=True)
    assert calls == 2  # クールダウン中
    clock.now = 30
    await store.fetch("k", loader, ttl=15)
    assert calls == 3


async def test_failure_keeps_previous_value():
    store = SnapshotStore(Clock())
    snap = await store.fetch("k", lambda: asyncio.sleep(0, result=["ok"]), ttl=0)

    async def boom():
        raise RuntimeError("squeue timeout")

    snap = await store.fetch("k", boom, ttl=0)
    assert snap.value == ["ok"]
    assert snap.last_error == "squeue timeout"
    assert snap.is_stale
