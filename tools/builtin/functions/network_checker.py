"""
network_checker - 工具

可直接调用:
    exec_network_checker(args) -> str
"""
import json, os, urllib.request, urllib.parse

# ===== 工具定义 =====
TOOLS = [
    {
            "name": "network_checker",
            "description": "网络工具：连接检测、网站可达性、域名提取",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "操作: check_connection, check_website, get_domain"},
                    "url": {"type": "string", "description": "URL地址"}
                },
                "required": ["action"]
            }
        },
]

def exec_network_checker(args):
    """网络检测工具 — 可直接调用
    
    @param args: dict - {"action": "check_connection|check_website|get_domain", "url": "..."}
    @return str - 检测结果
    """
    action = args.get("action", "")
    url = args.get("url", "https://www.baidu.com")
    try:
        if action == "check_connection":
            req = urllib.request.Request("https://www.baidu.com", method="HEAD")
            urllib.request.urlopen(req, timeout=5)
            return "网络连接正常"
        elif action == "check_website":
            if not url:
                return "请提供URL"
            req = urllib.request.Request(url, method="HEAD")
            resp = urllib.request.urlopen(req, timeout=10)
            return f"网站可达: {url} (状态码: {resp.getcode()})"
        elif action == "get_domain":
            parsed = urllib.parse.urlparse(url if url else "https://example.com")
            return f"域名: {parsed.netloc}"
        return f"未知操作: {action}"
    except Exception as e:
        return f"网络检查失败: {e}"

