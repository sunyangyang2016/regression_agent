"""
MCPTool - MCP 工具描述类
"""
from typing import Optional


class MCPTool:
    """MCP 工具描述"""
    def __init__(self, name: str, description: str = "", parameters: dict = None):
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}