"""
MCP 环境变量配置工具 — 弹窗让用户输入 API Key 等密钥
"""
import json

NAME = "mcp_env_setup"
DESCRIPTION = "弹出环境变量输入框，让用户填写 API Key 等配置信息"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mcp_env_setup",
            "description": "弹出对话框让用户填写环境变量（如 API Key），并保存到安装上下文中供后续 finalizeMCPInstall 使用",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "服务器 ID"
                    },
                    "env_vars": {
                        "type": "string",
                        "description": "JSON 格式的环境变量数组，每个元素包含 name(变量名)、description(说明)、required(是否必填)、default(默认值)、url(获取地址)。示例: [{\"name\":\"API_KEY\",\"description\":\"从官网获取的密钥\",\"required\":true,\"url\":\"https://example.com\"}]"
                    }
                },
                "required": ["server_id", "env_vars"]
            }
        }
    }
]

_mcp_bridge = None

# 记录已经弹出过对话框的 server_id，防止重复弹窗
_shown_dialogs = set()

def set_mcp_bridge(bridge):
    global _mcp_bridge
    _mcp_bridge = bridge

def mcp_env_setup(arguments: dict) -> str:
    """弹出环境变量配置对话框（不阻塞，直接返回。用户确认后自动向 AI 发送消息继续）"""
    global _mcp_bridge
    
    server_id = arguments.get("server_id", "")
    env_vars_str = arguments.get("env_vars", "[]")
    
    print(f"[mcp_env_setup] 被调用: server_id={server_id}")
    print(f"[mcp_env_setup] _mcp_bridge 是否存在: {_mcp_bridge is not None}")
    
    if not server_id:
        print(f"[mcp_env_setup] ❌ server_id 为空")
        return "❌ 请提供 server_id 参数"
    
    # ====== 参数错误检测 ======
    # 检测 [object Object] 等无效参数
    env_str_check = env_vars_str if isinstance(env_vars_str, str) else json.dumps(env_vars_str)
    if '[object Object]' in env_str_check or '[object Array]' in env_str_check:
        print(f"[mcp_env_setup] ❌ 收到无效参数: {env_str_check[:100]}")
        return "❌ 参数格式错误：env_vars 包含无效的 [object Object]，请重新传入正确的 JSON 格式环境变量数组"
    
    try:
        env_vars = json.loads(env_vars_str) if isinstance(env_vars_str, str) else env_vars_str
        if not isinstance(env_vars, (list, tuple)):
            print(f"[mcp_env_setup] ❌ env_vars 不是数组: {type(env_vars)}")
            return f"❌ env_vars 必须是数组，请传入正确的 JSON 格式"
        print(f"[mcp_env_setup] 解析到 {len(env_vars)} 个环境变量")
    except Exception as e:
        print(f"[mcp_env_setup] ❌ JSON 解析失败: {e}")
        return f"❌ env_vars JSON 解析失败: {e}"
    
    if not env_vars:
        print(f"[mcp_env_setup] ❌ env_vars 为空数组")
        return "❌ env_vars 为空，请指定需要填写的环境变量"
    
    # ====== 防止重复弹窗 ======
    if server_id in _shown_dialogs:
        print(f"[mcp_env_setup] ⚠️ 对话框已弹出过，跳过重复调用")
        return "⏳ 环境变量对话框已经弹出过，请先在对话框中填写并确认"
    _shown_dialogs.add(server_id)
    
    if not _mcp_bridge:
        print(f"[mcp_env_setup] ❌ MCPBridge 未就绪")
        return "❌ MCPBridge 未就绪"
    
    # 通知前端弹出对话框（直接生成 JS 对象字面量）
    env_json = json.dumps(env_vars, ensure_ascii=False)
    server_js = json.dumps(server_id, ensure_ascii=False)
    js = f"showAPIKeyDialog({{server_id:{server_js},env_vars:{env_json}}});"
    print(f"[mcp_env_setup] 执行 JS: {js[:200]}...")
    _mcp_bridge.execute_js(js)
    print(f"[mcp_env_setup] ✅ 对话框已弹出，用户确认后将自动继续")
    
    # 不阻塞，立即返回！用户确认后 confirmEnvVars 会发消息让 AI 继续
    return "⏳ 已弹出环境变量配置窗口，请用户填写后点击确认，确认后会自动继续安装"
