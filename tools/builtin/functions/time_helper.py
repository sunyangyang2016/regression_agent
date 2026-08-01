"""
time_helper - 工具

可直接调用:
    exec_time_helper(args) -> str
"""
import time
import json, os
import time, datetime

# ===== 工具定义 =====
TOOLS = [
    {
      "name": "time_helper",
      "description": "时间工具：获取时间戳、格式化时间、时间差计算",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {
            "type": "string",
            "description": "操作: now, timestamp, format_date, time_ago"
          },
          "format": {
            "type": "string",
            "description": "时间格式（format_date用），如 YYYY-MM-DD"
          }
        },
        "required": [
          "action"
        ]
      ,
        "display": {"name_cn": "时间工具", "description_cn": "时间戳转换/格式化/时间差", "icon": "fa-hourglass"}}
    ,
        "display": {"name_cn": "时间工具", "description_cn": "时间戳转换/格式化/时间差", "icon": "fa-hourglass"}},
]

def exec_time_helper(args):
    action = args.get('action', '')
    if not action:
        return '请提供 action'
    try:
        if action == 'now':
            return time.strftime('%Y-%m-%d %H:%M:%S')
        elif action == 'timestamp':
            return str(int(time.time()))
        elif action == 'format_date':
            fmt = args.get('format', 'YYYY-MM-DD')
            for k, v in _FMT_MAP.items():
                fmt = fmt.replace(k, v)
            return time.strftime(fmt)
        elif action == 'time_ago':
            ts = args.get('timestamp', 0)
            if not ts:
                ts = time.time()
            diff = time.time() - float(ts)
            if diff < 60:
                return f'{int(diff)}秒前'
            if diff < 3600:
                return f'{int(diff / 60)}分钟前'
            if diff < 86400:
                return f'{int(diff / 3600)}小时前'
            return f'{int(diff / 86400)}天前'
        return f'未知操作: {action}'
    except Exception as e:
        return f'失败: {e}'

