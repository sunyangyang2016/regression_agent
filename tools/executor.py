"""
工具执行器 - 异步执行、超时控制
"""
import asyncio
from typing import Callable, Dict


class ToolExecutor:
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._timeout = 30.0
    
    def register(self, name: str, handler: Callable):
        self._handlers[name] = handler
    
    async def execute(self, name: str, arguments: dict) -> str:
        handler = self._handlers.get(name)
        if not handler:
            return f"⚠️ 工具 '{name}' 未注册"
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(handler, arguments) if not asyncio.iscoroutinefunction(handler) else handler(arguments),
                timeout=self._timeout
            )
            return str(result)
        except asyncio.TimeoutError:
            return f"❌ 工具 '{name}' 执行超时"
        except Exception as e:
            return f"❌ 工具 '{name}' 执行失败: {e}"