"""
get_weather - 天气查询工具

可直接调用:
    get_weather(city) -> str
"""
import os, urllib.request, urllib.parse

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如 北京、Shanghai、London"}
                },
                "required": ["city"]
            }
        },
        "display": {"name_cn": "天气查询", "description_cn": "查询指定城市的实时天气", "icon": "fa-cloud-sun"}
    }
]

def get_weather(city):
    """查询天气 — 可直接调用
    
    @param city: str - 城市名称
    @return str - 天气信息
    """
    if isinstance(city, dict):
        city = city.get("city", "")
    if not city:
        return "请提供城市名称"
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%C+%t+%h+%w&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8").strip()
            if data:
                return f"{city} 天气: {data}"
            return f"{city}: 无法获取天气信息"
    except Exception as e:
        return f"查询失败: {e}"