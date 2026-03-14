"""
WebSocket Connection Manager

Maintains an in-memory map of submission_id → set of active WebSocket connections.
When the webhook fires (worker finished), it calls broadcast() to push the result
to every connected browser tab for that submission and closes the sockets.

Production note: For multi-worker deployments (e.g. multiple uvicorn processes),
replace the in-process dict with a Redis pub/sub channel — the public interface
(connect / disconnect / broadcast) stays identical.
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import DefaultDict, Set, Union

import redis.asyncio as redis
from fastapi import WebSocket

from .config import REDIS_URL

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._active: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        self.redis = None
        self.pubsub = None
        self._listener_task = None

    async def startup(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        self._listener_task = asyncio.create_task(self._listen_to_redis())

    async def shutdown(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()

    async def _listen_to_redis(self):
        try:
            await self.pubsub.subscribe("dummy_channel")

            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    data = message["data"]
                    
                    sockets = list(self._active.get(channel, []))
                    if not sockets:
                        continue
                    
                    for ws in sockets:
                        try:
                            await ws.send_text(data)
                            await ws.close()
                        except Exception:
                            logger.debug("Failed to send WS message to one client for id %s", channel)
                    
                    self._active.pop(channel, None)
                    await self.pubsub.unsubscribe(channel)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Redis listener task failed: %s", e)

    async def connect(self, submission_id: Union[int, str], ws: WebSocket) -> None:
        await ws.accept()
        channel = str(submission_id)
        
        if not self._active[channel]:
            if self.pubsub:
                await self.pubsub.subscribe(channel)

        self._active[channel].add(ws)
        logger.info("WS connected for id %s (total=%d)", channel, len(self._active[channel]))

    def disconnect(self, submission_id: Union[int, str], ws: WebSocket) -> None:
        channel = str(submission_id)
        if channel in self._active:
            self._active[channel].discard(ws)
            if not self._active[channel]:
                del self._active[channel]
                if self.pubsub:
                    asyncio.create_task(self.pubsub.unsubscribe(channel))
        logger.info("WS disconnected for id %s", channel)

    async def cache_result(self, submission_id: Union[int, str], data: dict) -> None:
        """Store the verdict in Redis with a 60-second TTL so late WebSocket
        connections can still pick it up (fixes the race condition)."""
        if self.redis:
            key = f"result:{submission_id}"
            await self.redis.set(key, json.dumps(data), ex=60)

    async def get_cached_result(self, submission_id: Union[int, str]) -> dict | None:
        """Return the cached verdict for *submission_id*, or None."""
        if self.redis:
            key = f"result:{submission_id}"
            raw = await self.redis.get(key)
            if raw:
                return json.loads(raw)
        return None

    async def broadcast(self, submission_id: Union[int, str], data: dict) -> None:
        channel = str(submission_id)
        message = json.dumps(data)

        # Cache first — ensures late WebSocket connections can still read the result
        await self.cache_result(submission_id, data)

        if self.redis:
            await self.redis.publish(channel, message)
        else:
            sockets = list(self._active.get(channel, []))
            for ws in sockets:
                try:
                    await ws.send_text(message)
                    await ws.close()
                except Exception:
                    pass
            self._active.pop(channel, None)


# Singleton
manager = ConnectionManager()
