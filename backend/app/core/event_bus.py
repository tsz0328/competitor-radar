"""通知中心事件总线：按配置选择进程内队列或 Redis pub/sub。

高优情报事件落库时由 analyzer 广播给相应用户，SSE 连接收到后重算未读数并推给前端。
单进程 / 单 worker 使用内存队列；多 worker / 多副本使用 Redis pub/sub 跨进程广播。

Redis 不可用（连不上 / 中途断开）时，RedisEventBus 会自愈降级为进程内总线，
保证单实例内 SSE 实时通知与 analyzer 主流程都不中断；降级只告警一次、不自动
切回，需重启进程恢复——多副本下跨实例通知会在降级期间失效，故生产仍应保证 Redis 可用。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from app.core.config import get_settings

try:  # 未启用 Redis 时不硬依赖该包，仅降级到 memory 后端时也不会被 import 阻断
    from redis.exceptions import RedisError as _RedisError
except ImportError:  # pragma: no cover - requirements 已声明 redis，此处仅兜底
    _RedisError = None  # type: ignore[assignment]

# 会触发降级的连接类异常：Redis 自身异常 + 底层网络错误 + 超时
if _RedisError is None:  # pragma: no cover
    _CONNECTION_ERRORS: tuple[type[BaseException], ...] = (
        OSError,
        asyncio.TimeoutError,
    )
else:
    _CONNECTION_ERRORS = (_RedisError, OSError, asyncio.TimeoutError)

logger = logging.getLogger(__name__)


def _channel(user_id: int) -> str:
    return f"competitor-radar:events:{user_id}"


class MemoryEventBus:
    def __init__(self) -> None:
        # user_id -> 该用户的 SSE 连接队列集合
        self._queues: dict[int, set[asyncio.Queue]] = defaultdict(set)

    async def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[user_id].add(q)
        return q

    async def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        self._queues.get(user_id, set()).discard(q)

    async def publish(self, user_id: int, payload: dict[str, Any]) -> None:
        for q in list(self._queues.get(user_id, ())):
            await q.put(payload)

    async def aclose(self) -> None:
        self._queues.clear()


class RedisEventBus:
    """Redis pub/sub 总线；Redis 不可用时自愈降级为进程内总线。

    多副本部署必须保证 Redis 可用，否则降级后只能同进程内广播，跨实例实时
    通知会失效（日志会显式告警）。降级是一次性的：进入降级态后不再尝试 Redis，
    也不会自动切回，需重启进程恢复——故障态下以简单可靠优先。
    """

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)
        # 进程内兜底总线：Redis 不可用时接管订阅与发布，保证单实例可用
        self._fallback = MemoryEventBus()
        self._degraded = False
        self._subscriptions: dict[
            int, dict[asyncio.Queue, tuple[Any, asyncio.Task]]
        ] = {}  # 驱动 pubsub 类型不定，不在此处公开具体类型

    def _mark_degraded(self, reason: str) -> None:
        """首次降级时告警一次，之后静默，避免每条消息/每次订阅刷屏。"""
        if self._degraded:
            return
        self._degraded = True
        logger.warning(
            "Redis 通知总线不可用，已降级为进程内总线（%s）。"
            "多副本部署下跨实例实时通知将失效，直至 Redis 恢复并重启进程。",
            reason,
        )

    async def subscribe(self, user_id: int) -> asyncio.Queue:
        if self._degraded:
            return await self._fallback.subscribe(user_id)
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(_channel(user_id))
        except _CONNECTION_ERRORS as exc:
            self._mark_degraded(f"订阅失败：{exc}")
            return await self._fallback.subscribe(user_id)
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(self._reader(pubsub, queue))
        self._subscriptions.setdefault(user_id, {})[queue] = (pubsub, task)
        return queue

    async def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        entries = self._subscriptions.get(user_id)
        item = entries.pop(queue, None) if entries else None
        if item is None:
            # 该队列来自降级兜底（或已退订），交给内存总线清理
            await self._fallback.unsubscribe(user_id, queue)
            return
        pubsub, task = item
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            await pubsub.unsubscribe(_channel(user_id))
        finally:
            await pubsub.aclose()

    async def publish(self, user_id: int, payload: dict[str, Any]) -> None:
        if self._degraded:
            await self._fallback.publish(user_id, payload)
            return
        try:
            await self._redis.publish(
                _channel(user_id), json.dumps(payload, ensure_ascii=False)
            )
        except _CONNECTION_ERRORS as exc:
            # 关键：不向上抛，避免中断 analyzer 的事件落库主流程
            self._mark_degraded(f"发布失败：{exc}")
            await self._fallback.publish(user_id, payload)

    async def _reader(self, pubsub, queue: asyncio.Queue) -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    await queue.put(json.loads(message.get("data") or "null"))
                except (json.JSONDecodeError, TypeError):
                    logger.warning("收到无法解析的通知事件消息")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # 订阅连接中途断开：标记降级，后续发布改走进程内兜底
            self._mark_degraded("订阅连接中断")
            logger.exception("Redis 通知订阅连接异常")

    async def aclose(self) -> None:
        for user_id, entries in list(self._subscriptions.items()):
            for queue in list(entries):
                await self.unsubscribe(user_id, queue)
        await self._fallback.aclose()
        try:
            await self._redis.aclose()
        except Exception:  # noqa: BLE001
            logger.warning("关闭 Redis 通知连接时出错", exc_info=True)


def _build_bus() -> MemoryEventBus | RedisEventBus:
    settings = get_settings()
    if settings.cache_backend.strip().lower() == "redis":
        logger.info("通知事件总线：Redis pub/sub (%s)", settings.redis_url)
        return RedisEventBus(settings.redis_url)
    logger.info("通知事件总线：进程内队列（单 worker）")
    return MemoryEventBus()


bus = _build_bus()
