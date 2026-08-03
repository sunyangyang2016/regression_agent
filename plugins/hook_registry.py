"""
钩子注册中心 - 插件事件钩子管理
支持同步 trigger 与异步 atrigger 双通道，同步/异步 handler 均可注册。
载荷与返回值统一使用 JSON 字符串传输。
"""
import asyncio
import inspect
import json
import threading
from typing import Any, Callable, Dict, List


class HookRegistry:
    """钩子注册中心（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._hooks: Dict[str, List[Callable]] = {}
            # 后台事件循环：供同步 trigger 驱动异步 handler 使用
            cls._instance._event_loop = None
            cls._instance._loop_thread = None
        return cls._instance

    # ==========================================
    # 后台事件循环管理（参照 AIClient._get_or_create_loop 模式）
    # ==========================================

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """获取或创建后台事件循环（线程安全）"""
        if self._event_loop is None or self._event_loop.is_closed():
            self._event_loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._event_loop.run_forever,
                daemon=True,
                name="hook-loop"
            )
            self._loop_thread.start()
        return self._event_loop

    # ==========================================
    # 注册 / 注销
    # ==========================================

    def register(self, hook_name: str, handler: Callable):
        """注册钩子处理器"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(handler)

    def unregister(self, hook_name: str, handler: Callable):
        """注销钩子处理器"""
        if hook_name in self._hooks:
            self._hooks[hook_name] = [h for h in self._hooks[hook_name] if h is not handler]

    def get_hooks(self, hook_name: str) -> List[Callable]:
        return self._hooks.get(hook_name, [])

    def clear(self):
        self._hooks.clear()

    # ==========================================
    # 触发（同步 / 异步双通道）
    # ==========================================

    def _normalize_result(self, r: Any) -> str:
        """统一将 handler 返回值规范为 JSON 字符串"""
        if r is None:
            return None
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)

    def _call_handler(self, handler: Callable, payload_json: str) -> Any:
        """同步调用单个 handler；同步/异步 handler 均支持"""
        if inspect.iscoroutinefunction(handler):
            loop = self._get_loop()
            fut = asyncio.run_coroutine_threadsafe(handler(payload_json), loop)
            return fut.result()
        return handler(payload_json)

    async def _call_handler_async(self, handler: Callable, payload_json: str) -> Any:
        """异步调用单个 handler；同步/异步 handler 均支持"""
        if inspect.iscoroutinefunction(handler):
            return await handler(payload_json)
        return handler(payload_json)

    def trigger(self, hook_name: str, payload_json: str = None) -> List[str]:
        """同步触发钩子（供 ChatController 等同步业务方使用）

        统一约定：入参 payload 为 JSON 字符串；返回结果为 JSON 字符串列表。
        同步/异步 handler 均可注册，异步 handler 由后台事件循环驱动。
        """
        results = []
        for handler in self._hooks.get(hook_name, []):
            try:
                r = self._call_handler(handler, payload_json)
                normalized = self._normalize_result(r)
                if normalized is not None:
                    results.append(normalized)
            except Exception as e:
                print(f"[Hook] 钩子 '{hook_name}' 执行失败: {e}")
        return results

    async def atrigger(self, hook_name: str, payload_json: str = None) -> List[str]:
        """异步触发钩子（供 ToolDispatcher/MCPDispatcher 等异步业务方使用）

        统一约定：入参 payload 为 JSON 字符串；返回结果为 JSON 字符串列表。
        同步/异步 handler 均可注册。
        """
        results = []
        for handler in self._hooks.get(hook_name, []):
            try:
                r = await self._call_handler_async(handler, payload_json)
                normalized = self._normalize_result(r)
                if normalized is not None:
                    results.append(normalized)
            except Exception as e:
                print(f"[Hook] 钩子 '{hook_name}' 执行失败: {e}")
        return results

    # ==========================================
    # 结果解析辅助
    # ==========================================

    @staticmethod
    def parse_results(results: List[str]) -> List[dict]:
        """将触发返回的 JSON 字符串列表解析为 dict 列表（容错跳过非法 JSON）"""
        parsed = []
        for r in results:
            try:
                parsed.append(json.loads(r) if isinstance(r, str) else r)
            except json.JSONDecodeError:
                continue
        return parsed