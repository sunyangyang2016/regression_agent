"""
MCP 标准协议模块
封装 JSON-RPC 消息构建和响应解析
"""
from tools.mcp.protocols.messages import (
    PROTOCOL_VERSION,
    build_initialize,
    build_initialized_notification,
    build_tools_list,
    build_tools_call,
)

from tools.mcp.protocols.parser import (
    parse_initialize_response,
    parse_tools_list_response,
    parse_tools_call_response,
    get_tool_capabilities,
    server_info_string,
)

__all__ = [
    "PROTOCOL_VERSION",
    "build_initialize",
    "build_initialized_notification",
    "build_tools_list",
    "build_tools_call",
    "parse_initialize_response",
    "parse_tools_list_response",
    "parse_tools_call_response",
    "get_tool_capabilities",
    "server_info_string",
]
