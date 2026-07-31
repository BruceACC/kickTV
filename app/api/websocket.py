"""
KickTV — WebSocket Endpoints

Real-time log streaming and status updates via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


from app.core.system_monitor import monitor
from app.core.queue_manager import queue
from app.logger import log_broadcaster
from app.utils.helpers import format_uptime

logger = logging.getLogger("kicktv")

ws_router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {
            "logs": [],
            "status": [],
        }

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = []
        self._connections[channel].append(websocket)
        logger.debug("WebSocket connected: %s (total: %d)", channel, len(self._connections[channel]))

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        if channel in self._connections:
            if websocket in self._connections[channel]:
                self._connections[channel].remove(websocket)
        logger.debug("WebSocket disconnected: %s", channel)

    async def broadcast(self, channel: str, message: dict) -> None:
        """Send message to all connections in a channel."""
        if channel not in self._connections:
            return
        dead: list[WebSocket] = []
        for ws in self._connections[channel]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[channel].remove(ws)

    @property
    def log_connections(self) -> int:
        return len(self._connections.get("logs", []))

    @property
    def status_connections(self) -> int:
        return len(self._connections.get("status", []))


manager = ConnectionManager()


@ws_router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time log streaming.
    Sends new log entries as they arrive.
    """
    await manager.connect(websocket, "logs")

    # Send recent logs as initial payload
    try:
        recent = log_broadcaster.get_recent(50)
        await websocket.send_json({"type": "initial", "data": recent})
    except Exception:
        pass

    # Register a callback to forward new logs
    log_queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_log(entry: dict) -> None:
        try:
            log_queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass

    log_broadcaster.register(on_log)

    try:
        while True:
            # Forward log entries from the queue
            try:
                entry = await asyncio.wait_for(log_queue.get(), timeout=30)
                await websocket.send_json({"type": "log", "data": entry})
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket logs error: %s", e)
    finally:
        log_broadcaster.unregister(on_log)
        manager.disconnect(websocket, "logs")


@ws_router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time status updates.
    Sends system stats and stream status every 2 seconds.
    """
    await manager.connect(websocket, "status")

    try:
        while True:
            try:
                system = monitor.get_stats()

                # Determine current and next video from queue
                # For Web TV, the queue is the source of truth
                current_video = None
                
                # We can't know exactly what OBS is playing, but we can peek at the queue
                peek_item = queue.peek()
                
                if peek_item:
                    current_video = {
                        "title": peek_item.title,
                        "author": peek_item.author,
                        "category": peek_item.category.value,
                        "provider": peek_item.provider.value,
                        "duration": peek_item.duration,
                        "thumbnail": peek_item.thumbnail,
                    }

                payload = {
                    "type": "status",
                    "data": {
                        "state": "live",
                        "current_video": current_video,
                        "next_video": None,
                        "fps": 30,
                        "bitrate": 0,
                        "frames_dropped": 0,
                        "total_videos_played": 0,
                        "reconnect_count": 0,
                        "uptime": "OBS Controlled",
                        "queue_size": queue.size,
                        "cpu_percent": system.cpu_percent,
                        "ram_percent": system.ram_percent,
                        "ram_used_mb": system.ram_used_mb,
                        "disk_percent": system.disk_percent,
                        "ffmpeg_cpu": 0,
                        "ffmpeg_ram_mb": 0,
                    },
                }

                await websocket.send_json(payload)
                await asyncio.sleep(2)

            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket status error: %s", e)
    finally:
        manager.disconnect(websocket, "status")
