"""
data_validator - 数据验证工具

可直接调用:
    data_validator(args) -> str
"""
import re

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "data_validator",
            "description": "数据验证：邮箱/URL 验证，文件名清理",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "操作: validate_email, validate_url, sanitize_filename"},
                    "value": {"type": "string", "description": "要验证或处理的值"}
                },
                "required": ["action", "value"]
            }
        },
        "display": {"name_cn": "数据验证", "description_cn": "验证邮箱/URL格式，清理文件名", "icon": "fa-check-circle"}
    }
]

def data_validator(args):
    """数据验证 — 可直接调用
    
    @param args: dict - {"action": "validate_email|validate_url|sanitize_filename", "value": "..."}
    @return str - 验证结果
    """
    action = args.get("action", "")
    value = args.get("value", "")
    if not action or not value:
        return "请提供 action 和 value"
    try:
        if action == "validate_email":
            pat = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return "有效邮箱" if re.match(pat, value) else "无效邮箱"
        elif action == "validate_url":
            pat = r'^https?://[\w.-]+(:\d+)?(/[\w./%-]*)?$'
            return "有效URL" if re.match(pat, value) else "无效URL"
        elif action == "sanitize_filename":
            clean = re.sub(r'[<>:"/\\|?*]', '_', value)
            clean = clean.strip('. ')
            return clean if clean else "无效文件名"
        return f"未知操作: {action}"
    except Exception as e:
        return f"失败: {e}"