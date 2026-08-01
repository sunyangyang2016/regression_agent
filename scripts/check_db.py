"""检查 mcp.db 数据库状态"""
import sqlite3
import json
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "database", "mcp.db")
cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_config", "defaults", "mcp_servers.json")

# 读取配置
with open(cfg_path, "r", encoding="utf-8") as f:
    config = json.load(f)
local_servers = config.get("mcpServers", {})
local_ids = set(local_servers.keys())

print("配置中的服务器:")
for sid in sorted(local_ids):
    print(f"  - {sid}")

print()

# 读取数据库
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, name, installed, github_repo_url FROM mcp_market ORDER BY created_at DESC").fetchall()

print(f"数据库中共 {len(rows)} 条市场数据:\n")
for r in rows:
    d = dict(r)
    name = d["name"]
    github_url = d["github_repo_url"] or ""
    
    matched = d["id"] in local_ids
    if not matched and name and name in local_ids:
        matched = True
    if not matched and github_url:
        repo_dir = github_url.rstrip('/').split('/')[-1].replace('.git', '').lower()
        matched = repo_dir in local_ids
    
    should_be = 1 if matched else 0
    status = "✅ 正确" if d["installed"] == should_be else "❌ 错误"
    print(f"  {status} {d['id']} ({name}): installed={d['installed']}, 应为={should_be}")

conn.close()