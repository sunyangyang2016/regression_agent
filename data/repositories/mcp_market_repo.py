"""
MCPMarketRepository - MCP 市场数据仓库
操作 mcp.db 中的 mcp_market 表
"""
import json
from datetime import datetime

from data.mcp_db import MCPDatabase


class MCPMarketRepository:
    """MCP 市场数据仓库"""

    def __init__(self):
        self.db = MCPDatabase()

    def get_all(self) -> list:
        """获取所有市场项"""
        cursor = self.db.connection.execute("SELECT * FROM mcp_market ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, item_id: str) -> dict:
        """根据 ID 获取市场项"""
        cursor = self.db.connection.execute(
            "SELECT * FROM mcp_market WHERE id = ?", (item_id,)
        )
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else {}

    def count(self) -> int:
        """获取市场项数量"""
        cursor = self.db.connection.execute("SELECT COUNT(*) as cnt FROM mcp_market")
        return cursor.fetchone()["cnt"]

    def upsert(self, item: dict):
        """插入或更新市场项"""
        now = datetime.now().isoformat()
        raw_issue = json.dumps(item.get("raw_issue", {}), ensure_ascii=False)
        labels = json.dumps(item.get("labels", []), ensure_ascii=False)

        self.db.connection.execute("""
            INSERT INTO mcp_market (
                id, name, title, github_repo_url, logo, description,
                author, issue_number, installed, tested, server_type,
                labels, created_at, raw_issue, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                title = excluded.title,
                github_repo_url = excluded.github_repo_url,
                logo = excluded.logo,
                description = excluded.description,
                author = excluded.author,
                issue_number = excluded.issue_number,
                installed = excluded.installed,
                tested = excluded.tested,
                server_type = excluded.server_type,
                labels = excluded.labels,
                created_at = excluded.created_at,
                raw_issue = excluded.raw_issue,
                fetched_at = excluded.fetched_at
        """, (
            item["id"],
            item.get("name", ""),
            item.get("title", ""),
            item.get("githubRepoUrl", ""),
            item.get("logo", ""),
            item.get("description", ""),
            item.get("author", ""),
            item.get("issueNumber", 0),
            1 if item.get("installed") else 0,
            1 if item.get("tested") else 0,
            item.get("serverType", ""),
            labels,
            item.get("createdAt", ""),
            raw_issue,
            now
        ))
        self.db.connection.commit()

    def upsert_many(self, items: list):
        """批量插入或更新"""
        for item in items:
            self.upsert(item)

    def clear(self):
        """清空所有市场数据"""
        self.db.connection.execute("DELETE FROM mcp_market")
        self.db.connection.commit()

    def _row_to_dict(self, row) -> dict:
        """将 SQLite Row 转换为字典"""
        d = dict(row)
        # 恢复 JSON 字段
        labels = d.get("labels")
        d["labels"] = json.loads(labels) if isinstance(labels, str) else []

        # 转换为前端期望的字段名格式
        return {
            "id": d["id"],
            "name": d["name"],
            "title": d["title"],
            "githubRepoUrl": d["github_repo_url"],
            "logo": d["logo"],
            "description": d["description"],
            "author": d["author"],
            "issueNumber": d["issue_number"],
            "installed": bool(d["installed"]),
            "tested": bool(d["tested"]),
            "serverType": d["server_type"],
            "labels": d["labels"],
            "createdAt": d["created_at"],
            "raw_issue": d["raw_issue"],
        }