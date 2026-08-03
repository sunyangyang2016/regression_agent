"""
内建工具调度器 - 异步执行内建工具调用
负责在收到 AI 的 tool_call 请求时，调度执行对应的内建工具
"""
import asyncio
import json
from typing import Dict, Callable, Awaitable


class ToolDispatcher:
    """内建工具调度器 - 异步执行内建工具
    
    主要职责：
    1. 维护内建工具名 → 处理器函数的映射
    2. 异步执行内建工具调用
    3. 支持动态注册/注销
    4. 支持超时和错误处理
    """
    
    def __init__(self):
        self._handlers: Dict[str, Callable[[dict], Awaitable[str]]] = {}
        self._timeout: float = 30.0  # 默认 30 秒超时
    
    def register(self, tool_name: str, handler: Callable[[dict], Awaitable[str]]):
        """注册内建工具处理器"""
        self._handlers[tool_name] = handler
    
    def register_sync(self, tool_name: str, handler: Callable[[dict], str]):
        """注册同步内建工具处理器（自动包装为异步，在线程池中执行避免阻塞事件循环）"""
        async def async_wrapper(args: dict) -> str:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, handler, args)
        self._handlers[tool_name] = async_wrapper
    
    def unregister(self, tool_name: str):
        """注销内建工具处理器"""
        self._handlers.pop(tool_name, None)
    
    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._handlers
    
    def get_tool_names(self) -> list:
        return list(self._handlers.keys())
    
    async def execute(self, tool_name: str, arguments: dict) -> str:
        """异步执行内建工具调用"""
        # ====== 工具权限校验（安全插件 hook 广播，内建工具链路） ======
        try:
            from plugins.hook_registry import HookRegistry
            results = await HookRegistry().atrigger("tool:before_execute", json.dumps(
                {"tool_name": tool_name, "arguments": arguments, "source": "builtin"}, ensure_ascii=False))
            for r in HookRegistry.parse_results(results):
                if not r.get("allowed", True):
                    print(f"[Dispatcher] 🛡️ 内建工具 '{tool_name}' 被安全策略拦截")
                    return r.get("deny_message", f"❌ 工具 '{tool_name}' 已被安全策略禁止")
        except Exception as e:
            print(f"[Dispatcher] ⚠️ 工具权限校验失败: {e}")

        handler = self._handlers.get(tool_name)
        if not handler:
            print(f"[Dispatcher] ⚠️ 内建工具 '{tool_name}' 未注册处理器")
            return f"⚠️ 内建工具 '{tool_name}' 未注册处理器"
        
        print(f"[Dispatcher] 🔍 找到内建处理器: {tool_name}")
        
        try:
            print(f"[Dispatcher] ⏳ 异步执行内建工具 '{tool_name}' (超时: {self._timeout}s)...")
            result = await asyncio.wait_for(
                handler(arguments),
                timeout=self._timeout
            )
            print(f"[Dispatcher] ✅ 内建工具 '{tool_name}' 执行成功")
            return str(result)
        except asyncio.TimeoutError:
            print(f"[Dispatcher] ❌ 内建工具 '{tool_name}' 执行超时 ({self._timeout}s)")
            return f"❌ 内建工具 '{tool_name}' 执行超时（{self._timeout}s）"
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Dispatcher] ❌ 内建工具 '{tool_name}' 执行失败: {e}")
            return f"❌ 内建工具 '{tool_name}' 执行失败: {str(e)}"
    
    def clear(self):
        """清除所有内建工具处理器"""
        self._handlers.clear()
    
    def set_timeout(self, timeout: float):
        """设置超时时间"""
        self._timeout = timeout
    
    async def execute_batch(self, calls: list) -> list:
        """批量执行内建工具调用
        
        Args:
            calls: [(tool_name, arguments), ...]
        
        Returns:
            [result_string, ...]
        """
        tasks = [self.execute(name, args) for name, args in calls]
        return await asyncio.gather(*tasks, return_exceptions=True)