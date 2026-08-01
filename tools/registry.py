"""
工具注册中心 - 管理所有工具的注册与查找
"""
from typing import Any, Callable, Dict, List, Optional


class ToolInfo:
    """工具信息"""
    def __init__(self, name: str, handler: Callable, description: str = "", schema: dict = None):
        self.name = name
        self.handler = handler
        self.description = description
        self.schema = schema or {}


class ToolRegistry:
    """工具注册中心 - 单例模式"""

    _instance = None
    _tools: Dict[str, ToolInfo] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, handler: Callable, description: str = "", schema: dict = None) -> bool:
        if name in self._tools:
            return False
        self._tools[name] = ToolInfo(name, handler, description, schema)
        return True

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> Optional[ToolInfo]:
        return self._tools.get(name)

    def get_all(self) -> List[ToolInfo]:
        return list(self._tools.values())

    def get_openai_tools(self) -> List[Dict]:
        """获取 OpenAI 格式的工具定义"""
        tools = []
        for info in self._tools.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": info.name,
                    "description": info.description,
                    "parameters": info.schema,
                },
            })
        return tools

    def contains(self, name: str) -> bool:
        return name in self._tools

    @property
    def count(self) -> int:
        return len(self._tools)