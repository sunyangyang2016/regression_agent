"""
string_processor - 字符串处理工具

可直接调用:
    string_processor(args) -> str
"""
import re, random, string as str_mod

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "string_processor",
            "description": "字符串处理：截断、随机生成、关键词提取、脱敏",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "操作: truncate, random_string, extract_keywords, mask_sensitive, camel_to_snake"},
                    "text": {"type": "string", "description": "文本"},
                    "length": {"type": "integer", "description": "长度"}
                },
                "required": ["action", "text"]
            }
        },
        "display": {"name_cn": "字符串处理", "description_cn": "截断/随机生成/关键词提取/脱敏", "icon": "fa-font"}
    }
]

def string_processor(args):
    """字符串处理 — 可直接调用
    
    @param args: dict - {"action": "truncate|random_string|...", "text": "...", "length": 10}
    @return str - 处理结果
    """
    action = args.get("action", "")
    text = args.get("text", "")
    length = args.get("length", 10)
    if not action or not text:
        return "请提供 action 和 text"
    try:
        if action == "truncate":
            return text[:max(0, length)] + ("..." if len(text) > length else "")
        elif action == "random_string":
            return ''.join(random.choices(str_mod.ascii_letters + str_mod.digits, k=max(1, length)))
        elif action == "extract_keywords":
            words = re.findall(r'[a-zA-Z]+', text)
            return ", ".join(sorted(set(words), key=len, reverse=True)[:5])
        elif action == "mask_sensitive":
            if len(text) <= 4:
                return text[0] + "***"
            return text[:2] + "****" + text[-2:]
        elif action == "camel_to_snake":
            return re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()
        return f"未知操作: {action}"
    except Exception as e:
        return f"失败: {e}"