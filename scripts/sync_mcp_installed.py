"""
直接更新 mcp.db 数据库中的 installed 字段
通过对比 mcp_servers.json 配置中的服务器名来匹配
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json

# 数据库路径
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "database", "mcp.db")

# 配置文件路径
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_config", "defaults", "mcp_servers.json")

print(f"📂 数据库: {db_path}")
print(f"📂 配置: {config_path}")

# 读取配置
if not os.path.exists(config_path):
    print(f"❌ 配置文件不存在: {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

local_servers = config.get("mcpServers", {})
local_ids = set(local_servers.keys())

print(f"📋 MCP 配置中服务器列表 ({len(local_ids)} 个):")
for sid in sorted(local_ids):
    cfg = local_servers[sid]
    print(f"   - {sid}: transport={cfg.get('transport','?')}, command={cfg.get('command','')[:30]}")

# 读取数据库
if not os.path.exists(db_path):
    print(f"❌ 数据库不存在: {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.execute("SELECT * FROM mcp_market ORDER BY created_at DESC")
rows = cursor.fetchall()

print(f"\n📋 数据库中共 {len(rows)} 条市场数据")

updated_count = 0
for row in rows:
    d = dict(row)
    item_id = d["id"]
    name = d.get("name", "")
    github_url = d.get("github_repo_url", "")
    
    # 匹配逻辑：ID / name / githubRepoUrl 目录名
    matched = item_id in local_ids
    if not matched and name and name in local_ids:
        matched = True
    if not matched and github_url:
        repo_dir = github_url.rstrip('/').split('/')[-1].replace('.git', '').lower()
        matched = repo_dir in local_ids
    
    installed = 1 if matched else 0
    current_installed = d.get("installed", 0)
    
    if installed != current_installed:
        conn.execute("UPDATE mcp_market SET installed = ? WHERE id = ?", (installed, item_id))
        print(f"   {'✅' if installed else '❌'} {item_id} ({name}): installed {current_installed} → {installed}")
        updated_count += 1
    else:
        status = '已安装' if installed else '未安装'
        print(f"   {'✓' if installed else '○'} {item_id} ({name}): {status} (无需更新)")

conn.commit()
conn.close()

print(f"\n✅ 完成！共更新 {updated_count} 条记录")