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
from typing import DefaultDict, Set

from typing import DefaultDict, Set, Union

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # submission_id (int) or run_id (str) → set of WebSocket connections
        self._active: DefaultDict[Union[int, str], Set[WebSocket]] = defaultdict(set)

    async def connect(self, submission_id: Union[int, str], ws: WebSocket) -> None:
        await ws.accept()
        self._active[submission_id].add(ws)
        logger.info("WS connected for id %s (total=%d)", submission_id, len(self._active[submission_id]))

    def disconnect(self, submission_id: Union[int, str], ws: WebSocket) -> None:
        self._active[submission_id].discard(ws)
        if not self._active[submission_id]:
            del self._active[submission_id]
        logger.info("WS disconnected for id %s", submission_id)

    async def broadcast(self, submission_id: Union[int, str], data: dict) -> None:
        """
        Push `data` as JSON to every WebSocket subscribed to this ID,
        then close each connection. Errors on individual sockets are swallowed
        so one bad client can't block others.
        """
        sockets = list(self._active.get(submission_id, []))
        if not sockets:
            return

        message = json.dumps(data)
        for ws in sockets:
            try:
                await ws.send_text(message)
                await ws.close()
            except Exception:
                logger.debug("Failed to send WS message to one client for id %s", submission_id)

        # Clean up
        self._active.pop(submission_id, None)


# Singleton — imported by routes.py
manager = ConnectionManager()
