"""Redis 后端集成测试（里程碑 11 多实例路径）。

开发机没有真 Redis 服务，用 fakeredis 注入内存 FakeRedis 来覆盖：
- RedisEventBus：跨「SSE 实例」广播、按用户隔离、退订、关闭
- RedisCache：分布式锁互斥、令牌释放、KV 基本操作

让 #11 的「多实例」路径不再零覆盖，能拦住 Redis 相关回归。
"""
import asyncio

import fakeredis.aioredis as fake_aioredis
import pytest
import redis
import redis.asyncio as aioredis

from app.core.cache import RedisCache
from app.core.event_bus import RedisEventBus


@pytest.fixture
def patch_redis(monkeypatch: pytest.MonkeyPatch):
    """把 redis.asyncio.from_url 重定向到 fakeredis 的内存实现（每个测试隔离）。"""
    server = fake_aioredis.FakeServer()

    def _fake_from_url(_url: str, **kwargs):
        return fake_aioredis.FakeRedis(
            server=server,
            decode_responses=kwargs.get("decode_responses", False),
        )

    monkeypatch.setattr(aioredis, "from_url", _fake_from_url)
    yield


async def test_redis_event_bus_cross_instance_broadcast(patch_redis: object) -> None:
    """多副本核心语义：实例 A 的高优事件，能被实例 B 的 SSE 订阅者收到。"""
    bus_producer = RedisEventBus("redis://fake")
    bus_consumer = RedisEventBus("redis://fake")

    q = await bus_consumer.subscribe(1)
    await bus_producer.publish(1, {"type": "event", "id": 7, "level": "high"})

    payload = await asyncio.wait_for(q.get(), timeout=2)
    assert payload == {"type": "event", "id": 7, "level": "high"}

    await bus_consumer.unsubscribe(1, q)
    await bus_consumer.aclose()
    await bus_producer.aclose()


async def test_redis_event_bus_user_isolation(patch_redis: object) -> None:
    """广播按 user_id 隔离：发给用户 1 的事件不会泄露到用户 2。"""
    bus = RedisEventBus("redis://fake")
    q1 = await bus.subscribe(1)
    q2 = await bus.subscribe(2)

    await bus.publish(1, {"type": "event", "id": 1})

    payload = await asyncio.wait_for(q1.get(), timeout=2)
    assert payload["id"] == 1
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q2.get(), timeout=0.3)

    await bus.unsubscribe(1, q1)
    await bus.unsubscribe(2, q2)
    await bus.aclose()


async def test_redis_event_bus_unsubscribe_stops_delivery(patch_redis: object) -> None:
    """退订后不再收到该用户的事件。"""
    bus = RedisEventBus("redis://fake")
    q = await bus.subscribe(1)

    await bus.publish(1, {"type": "event", "id": 1})
    assert (await asyncio.wait_for(q.get(), timeout=2))["id"] == 1

    await bus.unsubscribe(1, q)
    await bus.publish(1, {"type": "event", "id": 2})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.3)

    await bus.aclose()


async def test_redis_cache_lock_exclusivity(patch_redis: object) -> None:
    """同一把锁只能被一个实例抢到（多副本调度互斥）。"""
    cache = RedisCache("redis://fake")
    token1 = await cache.acquire("scheduler:crawl-tick", 600)
    assert token1 is not None

    token2 = await cache.acquire("scheduler:crawl-tick", 600)
    assert token2 is None  # 别人还持着，本轮跳过

    # 只有持有正确令牌才能释放；错误令牌返回 False（走 Lua 原子脚本）
    assert await cache.release("scheduler:crawl-tick", token1) is True
    assert await cache.release("scheduler:crawl-tick", "wrong-token") is False

    # 释放后可被重新抢到，且令牌不同
    token3 = await cache.acquire("scheduler:crawl-tick", 600)
    assert token3 is not None and token3 != token1

    await cache.delete("scheduler:crawl-tick")
    await cache.aclose()


async def test_redis_cache_kv(patch_redis: object) -> None:
    """Redis 后端的 get/set/delete 基本语义。"""
    cache = RedisCache("redis://fake")
    assert await cache.get("x") is None
    await cache.set("x", "v", ttl=10)
    assert await cache.get("x") == "v"
    await cache.delete("x")
    assert await cache.get("x") is None
    await cache.aclose()


class _FailingRedis:
    """模拟 Redis 完全不可用：建连即失败。"""

    def pubsub(self):  # type: ignore[no-untyped-def]
        raise redis.exceptions.ConnectionError("simulated redis down")

    async def publish(self, *_args, **_kwargs) -> None:
        raise redis.exceptions.ConnectionError("simulated redis down")

    async def aclose(self) -> None:
        return None


async def test_redis_bus_degrades_to_memory_on_subscribe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis 连不上时，SSE 订阅自愈降级到进程内总线，不再抛异常。"""
    monkeypatch.setattr(aioredis, "from_url", lambda *_a, **_k: _FailingRedis())
    bus = RedisEventBus("redis://down")

    q = await bus.subscribe(1)  # 不再抛 ConnectionError
    await bus.publish(1, {"type": "event", "id": 5})  # 降级后走内存兜底
    payload = await asyncio.wait_for(q.get(), timeout=2)
    assert payload == {"type": "event", "id": 5}
    assert bus._degraded is True

    await bus.unsubscribe(1, q)
    await bus.aclose()


async def test_redis_bus_publish_failure_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis 发布失败不冒泡（analyzer 主流程不中断），并降级到内存总线。"""
    server = fake_aioredis.FakeServer()
    real = fake_aioredis.FakeRedis(server=server, decode_responses=True)

    class _PubFailRedis:
        def pubsub(self):  # 订阅正常，仅发布失败
            return real.pubsub()

        async def publish(self, *_args, **_kwargs) -> None:
            raise redis.exceptions.ConnectionError("simulated publish failure")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(aioredis, "from_url", lambda *_a, **_k: _PubFailRedis())
    bus = RedisEventBus("redis://flaky")

    q = await bus.subscribe(1)  # 订阅成功
    # 发布失败不抛异常——高优事件落库不会因通知失败而中断
    await bus.publish(1, {"type": "event", "id": 9})
    assert bus._degraded is True

    # 降级后新订阅走内存兜底，能收到后续发布
    q2 = await bus.subscribe(1)
    await bus.publish(1, {"type": "event", "id": 10})
    assert (await asyncio.wait_for(q2.get(), timeout=2))["id"] == 10

    await bus.unsubscribe(1, q)
    await bus.unsubscribe(1, q2)
    await bus.aclose()
