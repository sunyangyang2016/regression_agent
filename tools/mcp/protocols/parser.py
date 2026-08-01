"""
MCP 协议响应解析工具

从 messages.py 分离出的响应解析函数集合。
"""
from typing import Optional, List
from tools.mcp.protocols.tool import MCPTool


def parse_initialize_response(response: dict) -> Optional[dict]:
    """解析 initialize 响应，返回 server_info 字典"""
    if not response or "error" in response:
        return None
    result = response.get("result", {})
    return {
        "server_info": result.get("serverInfo", {}),
        "capabilities": result.get("capabilities", {}),
        "protocol_version": result.get("protocolVersion"),
        "instructions": result.get("instructions", ""),
    }


def parse_tools_list_response(response: dict) -> List[MCPTool]:
    """解析 tools/list 响应，返回 MCPTool 列表"""
    tools = []
    if not response or "error" in response:
        return tools
    
    result = response.get("result", {})
    tools_list = result.get("tools", [])
    
    for t in tools_list:
        mt = MCPTool(
            name=t["name"],
            description=t.get("description", ""),
            parameters=t.get("inputSchema", {})
        )
        tools.append(mt)
    
    return tools


def parse_tools_call_response(response: dict) -> str:
    """解析 tools/call 响应，返回文本内容"""
    if not response:
        return "❌ 工具调用失败: 无响应"
    
    if "error" in response:
        err = response["error"]
        err_msg = err.get("message", "未知错误")
        err_code = err.get("code", "")
        return f"❌ 工具调用失败: [{err_code}] {err_msg}"
    
    result = response.get("result", {})
    content = result.get("content", [])
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    return "\n".join(texts)


def get_tool_capabilities(response: dict) -> bool:
    """检查 initialize 响应中是否声明了 tools 能力"""
    info = parse_initialize_response(response)
    if info:
        caps = info.get("capabilities", {})
        return bool(caps.get("tools", {}))
    return False


def server_info_string(response: dict) -> str:
    """从 initialize 响应中提取服务器信息字符串"""
    info = parse_initialize_response(response)
    if info:
        si = info["server_info"]
        name = si.get("name", "?")
        version = si.get("version", "?")
        return f"{name} v{version}"
    return "?"