"""
current_time - 当前时间工具

可直接调用:
    current_time(args) -> str
"""
import time, datetime

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "获取当前的日期和时间信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "description": "时间格式，如 YYYY-MM-DD HH:mm:ss"}
                }
            }
        },
        "display": {"name_cn": "当前时间", "description_cn": "获取当前日期和时间信息", "icon": "fa-clock"}
    }
]

def current_time(args):
    """获取当前日期时间 — 可直接调用

    @param args: dict - {"format": "full(默认)|date|time|YYYY-MM-DD|timestamp"}
    @return str - 格式化后的时间字符串
    """
    fmt = args.get("format", "full") if isinstance(args, dict) else "full"
    now = datetime.datetime.now()
    formats = {
        "full": lambda: now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": lambda: now.strftime("%Y-%m-%d"),
        "time": lambda: now.strftime("%H:%M:%S"),
        "YYYY-MM-DD": lambda: now.strftime("%Y-%m-%d"),
        "timestamp": lambda: str(int(now.timestamp())),
    }
    return formats.get(fmt, formats["full"])()