"""缓存抽象（里程碑 3.4 遗留项，随里程碑 11 一起落地）。

为什么需要它 —— 两个真实问题：
1. `docker-compose` / 多副本部署后，多个进程各有一份内存缓存，状态互不相通；
2. 更严重的：**每个副本都会拉起 APScheduler**，同一个监控页面会被重复抓取，
   既浪费带宽又可能被目标站点视为攻击。

所以调度任务在执行前先抢一把**分布式锁**：`CACHE_BACKEND=redis` 时用
`SET NX EX`（谁抢到谁干活，进程崩溃锁会自动过期，不会死锁）；
开发期没有 Redis，退回进程内 `MemoryCache`——单进程内照样互斥。

对外只暴露 5 个方法，换后端只改 `CACHE_BACKEND`，业务代码零改动。
"""
import asyncio
import logging
import time
import uuid
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Cache(Protocol):
    """缓存后端的统一接口（Protocol = 只约定形状，不强制继承）。"""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def acquire(self, name: str, ttl: int) -> str | None:
        """尝试获取名为 name 的锁，成功返回令牌，失败返回 None（不阻塞等待）。"""
        ...

    async def release(self, name: str, token: str) -> bool:
        """释放锁；只有持有正确令牌才能释放，避免误删别人的锁。"""
        ...


class MemoryCache:
    """进程内缓存。注意：多副本部署时各进程各一份，不能用于跨实例互斥。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}  # key -> (value, 过期时刻)
        self._locks: dict[str, tuple[str, float]] = {}  # name -> (token, 过期时刻)
        self._guard = asyncio.Lock()  # dict 本身不是线程/协程安全的，统一加锁

    @staticmethod
    def _now() -> float:
        return time.monotonic()  # 用单调时钟计 TTL，不受系统改时间影响

    async def get(self, key: str) -> str | None:
        async with self._guard:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if expire_at is not None and expire_at < self._now():
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expire_at = self._now() + ttl if ttl is not None else None
        async with self._guard:
            self._data[key] = (value, expire_at)

    async def delete(self, key: str) -> None:
        async with self._guard:
            self._data.pop(key, None)

    async def acquire(self, name: str, ttl: int) -> str | None:
        async with self._guard:
            held = self._locks.get(name)
            if held is not None and held[1] >= self._now():
                return None  # 别人还持着，直接放弃本轮
            token = uuid.uuid4().hex
            self._locks[name] = (token, self._now() + ttl)
            return token

    async def release(self, name: str, token: str) -> bool:
        async with self._guard:
            held = self._locks.get(name)
            if held is not None and held[0] == token:
                del self._locks[name]
                return True
            return False


class RedisCache:
    """Redis 后端：多副本部署时用它做跨实例互斥与共享缓存。"""

    # 原子地"校验令牌并删除"，避免 release 与过期/他人加锁竞态
    _RELEASE_SCRIPT = (
        "if redis.call('get', KEYS[1]) == ARGV[1] "
        "then return redis.call('del', KEYS[1]) else return 0 end"
    )

    def __init__(self, url: str) -> None:
        # 延迟导入：没装 redis 包也不影响 memory 后端的开发环境
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await self._client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def acquire(self, name: str, ttl: int) -> str | None:
        token = uuid.uuid4().hex
        # NX = 不存在才写入（抢锁）；EX = 到期自动释放，持有进程崩溃也不会死锁
        if await self._client.set(name, token, nx=True, ex=ttl):
            return token
        return None

    async def release(self, name: str, token: str) -> bool:
        return bool(await self._client.eval(self._RELEASE_SCRIPT, 1, name, token))

    async def aclose(self) -> None:
        await self._client.aclose()


_cache: Cache | None = None


def get_cache() -> Cache:
    """返回全局缓存单例（按 CACHE_BACKEND 选择后端）。"""
    global _cache
    if _cache is None:
        backend = settings.cache_backend.strip().lower()
        if backend == "redis":
            _cache = RedisCache(settings.redis_url)
            logger.info("缓存后端：redis (%s)", settings.redis_url)
        else:
            _cache = MemoryCache()
            if backend != "memory":
                logger.warning("未知 CACHE_BACKEND=%s，已退回 memory", backend)
            else:
                logger.info("缓存后端：memory（仅单进程互斥；多副本部署请设 CACHE_BACKEND=redis）")
    return _cache
