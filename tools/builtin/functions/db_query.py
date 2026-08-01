"""
db_query - 工具

可直接调用:
    exec_db_query(args) -> str
"""
import os
import hashlib, base64, secrets
import json, os
import subprocess
import math

# ===== 工具定义 =====
TOOLS = [
    {
      "name": "db_query",
      "description": "执行 SQL 数据库查询（需要配置 DATABASE_URL）",
      "parameters": {
        "type": "object",
        "properties": {
          "sql": {
            "type": "string",
            "description": "SQL 查询语句"
          }
        },
        "required": [
          "sql"
        ]
      ,
        "display": {"name_cn": "数据库查询", "description_cn": "执行SQL数据库查询", "icon": "fa-database"}}
    ,
        "display": {"name_cn": "数据库查询", "description_cn": "执行SQL数据库查询", "icon": "fa-database"}},
]

def exec_db_query(args):
    sql = args.get('sql', '')
    if not sql:
        return '请提供 SQL 语句'
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        return '未配置 DATABASE_URL'
    try:
        if db_url.startswith('sqlite'):
            import sqlite3
            path = db_url.replace('sqlite:///', '')
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            conn.close()
            if rows:
                lines = [str(r) for r in rows[:20]]
                return '查询结果:\n' + '\n'.join(lines)
            return '查询完成 (0 行)'
        return f"不支持的数据库: {db_url.split(':')[0]}"
    except ImportError as e:
        return f'缺少驱动: {e}'
    except Exception as e:
        return f'查询失败: {e}'

