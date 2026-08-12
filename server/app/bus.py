import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator

import redis.asyncio as aioredis

from .config import settings


def _channel(activity_id: str) -> str:
    return f"cutestar:events:{activity_id}"


class EventBus:
    """进程内事件总线；单 worker 或测试环境使用。"""

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    async def publish(self, activity_id: str, envelope: dict[str, object]) -> None:
        message = json.dumps(envelope, ensure_ascii=False)
        for queue in list(self._queues.get(activity_id, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, activity_id: str) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1024)
        self._queues[activity_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues[activity_id].discard(queue)
            if not self._queues[activity_id]:
                self._queues.pop(activity_id, None)

    async def aclose(self) -> None:
        self._queues.clear()


class RedisEventBus(EventBus):
    """Redis pub/sub 扇出；多 worker 部署时使用，WS 端仍以 DB 为准按序号补偿回放。"""

    def __init__(self, url: str) -> None:
        super().__init__()
        self._redis = aioredis.from_url(url, decode_responses=True)
        self._listeners: dict[str, asyncio.Task[None]] = {}

    async def publish(self, activity_id: str, envelope: dict[str, object]) -> None:
        await self._redis.publish(_channel(activity_id), json.dumps(envelope, ensure_ascii=False))

    async def subscribe(self, activity_id: str) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1024)
        self._queues[activity_id].add(queue)
        if activity_id not in self._listeners:
            self._listeners[activity_id] = asyncio.create_task(self._listen(activity_id))
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues[activity_id].discard(queue)
            if not self._queues[activity_id]:
                self._queues.pop(activity_id, None)
                listener = self._listeners.pop(activity_id, None)
                if listener is not None:
                    listener.cancel()

    async def _listen(self, activity_id: str) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_channel(activity_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                for queue in list(self._queues.get(activity_id, ())):
                    try:
                        queue.put_nowait(message["data"])
                    except asyncio.QueueFull:
                        pass
        finally:
            await pubsub.unsubscribe(_channel(activity_id))
            await pubsub.aclose()

    async def aclose(self) -> None:
        for listener in self._listeners.values():
            listener.cancel()
        self._listeners.clear()
        self._queues.clear()
        await self._redis.aclose()


bus: EventBus = RedisEventBus(settings.redis_url) if settings.redis_url else EventBus()
