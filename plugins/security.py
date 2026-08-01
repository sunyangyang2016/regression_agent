"""
插件安全检查
"""
import os
from typing import Optional
from plugins.base import BasePlugin


class PluginSecurity:
    """插件安全验证器"""

    BLOCKED_PATTERNS = ["os.system", "subprocess.call", "eval(", "exec(", "__import__"]

    def verify(self, plugin: BasePlugin) -> bool:
        """验证插件是否安全"""
        import inspect
        try:
            source = inspect.getsource(type(plugin))
            for pattern in self.BLOCKED_PATTERNS:
                if pattern in source:
                    print(f"[Security] 插件 '{plugin.name}' 包含危险代码: {pattern}")
                    return False
            return True
        except (OSError, TypeError):
            return True

    def sanitize_path(self, path: str) -> Optional[str]:
        """净化插件路径，防止路径穿越"""
        abs_path = os.path.abspath(path)
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if abs_path.startswith(base):
            return abs_path
        return None