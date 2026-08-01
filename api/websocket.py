"""
WebSocket 支持 - 实时通信
"""
import json
import asyncio
from typing import Any, Callable, Dict, Optional, Set


class WebSocketHandler:
    """WebSocket 处理器"""

    def __init__(self):
        self._connections: Set[Any] = set()
        self._handlers: Dict[str, Callable] = {}

    def register(self, event: str, handler: Callable):
        """注册事件处理器"""
        self._handlers[event] = handler

    def add_connection(self, ws):
        """添加连接"""
        self._connections.add(ws)

    def remove_connection(self, ws):
        """移除连接"""
        self._connections.discard(ws)

    async def handle_message(self, ws, message: str):
        """处理消息"""
        try:
            data = json.loads(message)
            event = data.get("event", "")
            payload = data.get("data", {})

            handler = self._handlers.get(event)
            if handler:
                result = await handler(payload)
                await self.send(ws, {"event": f"{event}:response", "data": result})
            else:
                await self.send(ws, {"event": "error", "data": {"message": f"未知事件: {event}"}})
        except json.JSONDecodeError:
            await self.send(ws, {"event": "error", "data": {"message": "无效的 JSON 格式"}})

    async def broadcast(self, event: str, data: Any):
        """广播消息"""
        message = json.dumps({"event": event, "data": data})
        for ws in self._connections.copy():
            try:
                await self.send(ws, {"event": event, "data": data})
            except Exception:
                self._connections.discard(ws)

    async def send(self, ws, data: Dict[str, Any]):
        """发送消息"""
        try:
            await ws.send(json.dumps(data, ensure_ascii=False))
        except Exception:
            self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)