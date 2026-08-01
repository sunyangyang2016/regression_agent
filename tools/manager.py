"""
工具管理器 - 统一接口
整合内建工具和MCP工具
"""
from tools.builtin.builtin_tools_manager import BuiltinManager
from tools.mcp.host import MCPHost


class ToolManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._builtin = BuiltinManager()
            cls._instance._mcp = MCPHost()
        return cls._instance
    
    def get_tools(self):
        """获取所有工具定义"""
        tools = []
        tools.extend(self._builtin.get_tools())
        tools.extend(self._mcp.get_tools())
        return tools
    
    def execute_tool(self, name: str, arguments: dict) -> str:
        """执行工具"""
        result = self._builtin.execute_tool(name, arguments)
        if "未注册" not in result and "未实现" not in result:
            return result
        return self._mcp.execute_tool(name, arguments)