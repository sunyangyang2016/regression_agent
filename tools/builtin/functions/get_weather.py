"""
get_weather - 天气查询工具

可直接调用:
    get_weather(city) -> str
"""
import json
import re
import urllib.request
import urllib.parse

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

def _strip_html(text):
    """剥离 HTML 标签并压缩空白"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def _fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")

def _parse_weather_json(data):
    """从 wttr.in JSON 数据中提取精简天气信息"""
    root = json.loads(data)
    current = root.get("current_condition", [{}])[0]

    weather_desc = current.get("lang_zh", [{}])[0].get("value")
    if not weather_desc:
        weather_desc = current.get("weatherDesc", [{}])[0].get("value", "未知")

    temp = current.get("temp_C", "-")
    feels = current.get("FeelsLikeC", "-")
    humidity = current.get("humidity", "-")
    wind_dir = current.get("winddir16Point", "-")
    wind_km = current.get("windspeedKmph", "-")

    parts = [
        f"{weather_desc}",
        f"温度{temp}°C",
        f"体感{feels}°C",
        f"湿度{humidity}%",
        f"风力{wind_dir} {wind_km}km/h",
    ]
    return "，".join(parts)

def get_weather(city):
    """查询天气 — 可直接调用

    @param city: str - 城市名称
    @return str - 天气信息
    """
    if isinstance(city, dict):
        city = city.get("city", "")
    if not city:
        return "请提供城市名称"

    encoded = urllib.parse.quote(city)
    # 优先使用 JSON 接口，输出精简
    try:
        data = _fetch(f"https://wttr.in/{encoded}?format=j1&lang=zh")
        info = _parse_weather_json(data)
        return f"{city} 天气: {info}"
    except Exception:
        pass

    # 兜底：文本接口 + HTML 清理，防止大段 HTML 进入上下文
    try:
        data = _fetch(f"https://wttr.in/{encoded}?format=%C+%t+%h+%w&lang=zh")
        info = _strip_html(data)
        # 限长 200 字符，避免异常返回撑爆上下文
        info = info[:200]
        if info:
            return f"{city} 天气: {info}"
    except Exception as e:
        return f"查询失败: {e}"

    return f"{city}: 无法获取天气信息"