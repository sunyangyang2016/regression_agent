"""
MCP 标准协议 - 消息构建

提供 JSON-RPC 消息的构建函数（响应解析见 parser.py）
"""
import json
from typing import Optional

# MCP 协议版本
PROTOCOL_VERSION = "2024-11-05"

# JSON-RPC 版本
JSONRPC_VERSION = "2.0"


def build_initialize(client_info: dict = None) -> str:
    """构建 initialize 请求 JSON 字符串"""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": client_info or {"name": "agent", "version": "1.0.0"}
        },
        "id": 1
    })


def build_initialized_notification() -> str:
    """构建 initialized 通知 JSON 字符串"""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "method": "notifications/initialized",
        "params": {}
    })


def build_tools_list() -> str:
    """构建 tools/list 请求 JSON 字符串"""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "method": "tools/list",
        "params": {},
        "id": 2
    })


def build_tools_call(name: str, arguments: dict, req_id: int = 3) -> str:
    """构建 tools/call 请求 JSON 字符串"""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
        "id": req_id
    })
