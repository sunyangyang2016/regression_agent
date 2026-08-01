"""
MCP 服务器安装工具 — 供 AI 自动分析和安装 MCP Server
完成安装
"""
import json
import os

NAME = "mcp_server_install"
DESCRIPTION = "MCP 服务器安装助手 — 完成安装"

# ==========================================
# 工具定义（1 个工具）
# ==========================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mcp_finalize_install",
            "description": "完成 MCP 服务器安装。提供完整的 MCP 服务器配置 JSON，后端直接将此配置写入 mcp_servers.json 并启动服务。请先使用 file_ops 工具分析完所有文件后再调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "市场项 ID（与 installMCPFromMarket 传入的一致）"
                    },
                    "config_json": {
                        "type": "string",
                        "description": "⚠️ 重要：请先仔细阅读该 MCP 服务器的官方文档（README.md、INSTALL.md、docs/ 等），按照文档中的配置说明来构造 JSON。\n\n必须遵循以下规则：\n1. 📖 严格按照 README.md 中的配置示例，逐字段复制，不要自己发明配置\n2. 📦 如果 README 推荐使用 `npx` 方式，必须使用 `\"command\": \"npx\"` + `\"args\": [\"-y\", \"包名\"]`\n3. 🐍 如果 README 推荐使用 `pip install` 安装 + `python -m` 运行，则使用 `\"command\": \"python\"` + `\"args\": [\"-m\", \"模块名\"]`；如果是 uvx 方式则使用 `\"command\": \"uvx\"` + `\"args\": [\"包名\"]`\n4. 📂 cwd 设置为服务器文件下载到的目录路径\n5. 🔑 如果文档提到需要环境变量（API Key 等），在 env 字段中留空字符串，后续会让用户填写\n6. ❌ 不要指定 enabled/auto_start 字段，后端会自动处理\n\n配置示例（仅作参考，最终以 README 中的说明为准）：\n\n【npx 方式】\n{\n  \"transport\": \"stdio\",\n  \"command\": \"npx\",\n  \"args\": [\"-y\", \"@humanity4ai/mcp-servers\"],\n  \"cwd\": \"E:\\\\path\\\\to\\\\server\",\n  \"name\": \"服务器名称\",\n  \"description\": \"描述\",\n  \"env\": {}\n}\n\n【pip/python 方式】\n{\n  \"transport\": \"stdio\",\n  \"command\": \"python\",\n  \"args\": [\"-m\", \"mcp_server\"],\n  \"cwd\": \"E:\\\\path\\\\to\\\\server\",\n  \"name\": \"服务器名称\",\n  \"description\": \"描述\",\n  \"env\": {}\n}\n\n【uvx 方式】\n{\n  \"transport\": \"stdio\",\n  \"command\": \"uvx\",\n  \"args\": [\"mcp-server-package\"],\n  \"cwd\": \"E:\\\\path\\\\to\\\\server\",\n  \"name\": \"服务器名称\",\n  \"description\": \"描述\",\n  \"env\": {}\n}\n\n【node 本地脚本】\n{\n  \"transport\": \"stdio\",\n  \"command\": \"node\",\n  \"args\": [\"dist/server.js\"],\n  \"cwd\": \"E:\\\\path\\\\to\\\\server\",\n  \"name\": \"服务器名称\",\n  \"description\": \"描述\",\n  \"env\": {}\n}\n\n【HTTP 远程】\n{\n  \"transport\": \"http\",\n  \"url\": \"https://example.com/mcp\",\n  \"name\": \"服务器名称\",\n  \"description\": \"描述\"\n}"
                    },
                    "extra_info": {
                        "type": "string",
                        "description": "额外提示信息（可选，会显示在前端日志中）"
                    }
                },
                "required": ["item_id", "config_json"]
            }
        }
    }
]


# ==========================================
# 全局 MCPBridge 引用（由 AIExecutor 注入）
# ==========================================
_mcp_bridge = None


def set_mcp_bridge(bridge):
    """由外部注入 MCPBridge 实例"""
    global _mcp_bridge
    _mcp_bridge = bridge


# ==========================================
# 工具执行函数
# ==========================================

def mcp_finalize_install(arguments: dict) -> str:
    """完成安装"""
    global _mcp_bridge
    item_id = arguments.get("item_id", "")
    config_json = arguments.get("config_json", "{}")
    extra_info = arguments.get("extra_info", "")
    if not item_id:
        return "❌ 请提供 item_id 参数"
    if _mcp_bridge:
        try:
            _mcp_bridge.finalizeMCPInstall(item_id, config_json, extra_info)
            return "✅ 安装指令已发送到后端，正在启动服务...请查看日志了解进度"
        except Exception as e:
            return f"❌ 安装失败: {str(e)}"
    return "❌ MCPBridge 未就绪"