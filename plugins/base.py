"""
插件基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BasePlugin(ABC):
    """插件基类 - 所有插件必须继承此类"""

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = []
    hooks: List[str] = []

    def __init__(self):
        self._enabled = True
        self._config: Dict[str, Any] = {}

    @abstractmethod
    def on_load(self):
        """插件加载时调用"""
        ...

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def on_enable(self):
        """插件启用时调用"""
        pass

    def on_disable(self):
        """插件禁用时调用"""
        pass

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "enabled": self._enabled,
        }