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
from typing import DefaultDict, Dict, Union

import redis.asyncio as redis
from fastapi import WebSocket

from .config import REDIS_URL

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # channel → { WebSocket: asyncio.Event }
        # The Event is set by broadcast() (or disconnect()) so the route
        # endpoint can unblock immediately without reading from the socket.
        self._active: DefaultDict[str, Dict[WebSocket, asyncio.Event]] = defaultdict(dict)
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
                    try:
                        parsed = json.loads(data)
                        close_after = parsed.pop("_close", True)
                    except (json.JSONDecodeError, TypeError):
                        close_after = True
                        parsed = {"raw": data}

                    payload = json.dumps(parsed)
                    connections = dict(self._active.get(channel, {}))
                    if not connections:
                        continue

                    for ws, done_event in connections.items():
                        try:
                            await ws.send_text(payload)
                            if close_after:
                                await ws.close()
                        except Exception:
                            logger.debug("Failed to send WS message to one client for id %s", channel)
                        finally:
                            if close_after:
                                done_event.set()

                    if close_after:
                        self._active.pop(channel, None)
                        await self.pubsub.unsubscribe(channel)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Redis listener task failed: %s", e)

    async def connect(self, submission_id: Union[int, str], ws: WebSocket) -> asyncio.Event:
        """
        Accept the WebSocket, register it, and return an asyncio.Event.
        The caller should await this event instead of looping on receive_text().
        The event is set when a final verdict is broadcast OR when the client
        disconnects early, so the endpoint always exits cleanly.
        """
        await ws.accept()
        channel = str(submission_id)
        done_event = asyncio.Event()

        if not self._active[channel]:
            if self.pubsub:
                await self.pubsub.subscribe(channel)

        self._active[channel][ws] = done_event
        logger.info("WS connected for id %s (total=%d)", channel, len(self._active[channel]))
        return done_event

    def disconnect(self, submission_id: Union[int, str], ws: WebSocket) -> None:
        channel = str(submission_id)
        if channel in self._active:
            done_event = self._active[channel].pop(ws, None)
            # Always set the event — handles early client disconnect (page refresh,
            # navigation) so the awaiting coroutine in routes.py unblocks.
            if done_event is not None:
                done_event.set()
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

    async def broadcast(
        self, submission_id: Union[int, str], data: dict, *, close_after: bool = True
    ) -> None:
        """
        Push data to WebSocket clients subscribed to submission_id/run_id.
        When close_after=True (default): send and close sockets (single result).
        When close_after=False: send without closing (streaming partial results).
        """
        channel = str(submission_id)
        payload = {**data, "_close": close_after}
        message = json.dumps(payload)

        # Cache only on final message — late connections get the last cached result
        if close_after:
            await self.cache_result(submission_id, data)

        if self.redis:
            await self.redis.publish(channel, message)
        else:
            # No Redis: deliver in-process and set done Events directly
            connections = dict(self._active.get(channel, {}))
            for ws, done_event in connections.items():
                try:
                    await ws.send_text(message)
                    if close_after:
                        await ws.close()
                except Exception:
                    pass
                finally:
                    if close_after:
                        done_event.set()
            if close_after:
                self._active.pop(channel, None)


# Singleton
manager = ConnectionManager()
