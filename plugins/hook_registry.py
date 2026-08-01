"""
钩子注册中心 - 插件事件钩子管理
"""
from typing import Any, Callable, Dict, List


class HookRegistry:
    """钩子注册中心"""

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {}

    def register(self, hook_name: str, handler: Callable):
        """注册钩子处理器"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(handler)

    def unregister(self, hook_name: str, handler: Callable):
        """注销钩子处理器"""
        if hook_name in self._hooks:
            self._hooks[hook_name] = [h for h in self._hooks[hook_name] if h is not handler]

    def trigger(self, hook_name: str, *args, **kwargs):
        """触发钩子"""
        handlers = self._hooks.get(hook_name, [])
        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception as e:
                print(f"[Hook] 钩子 '{hook_name}' 执行失败: {e}")

    def get_hooks(self, hook_name: str) -> List[Callable]:
        return self._hooks.get(hook_name, [])

    def clear(self):
        self._hooks.clear()