"""
MCP Market Repository — 经典 Repository 模式
持有 db（Database 连接池），使用原生 SQL 访问 mcp_market_index 表
保持与 MCPBridge 兼容的接口（get_all/get_by_id/count/upsert/...）
"""
import json
from typing import Any, Dict, List, Optional

from storage.database import Database


class MCPMarketRepository:
    """MCP 市场数据仓库（持有 db + 原生 SQL）"""

    TABLE = "mcp_market_index"  # 表名

    def __init__(self):
        self.db = Database()  # 直接持有数据库（连接池）

    # ==========================================
    # 查询
    # ==========================================

    def get_all(self) -> list:
        """获取所有市场项（按创建时间倒序）"""
        rows = self.db.query(f"SELECT * FROM {self.TABLE} ORDER BY created_at DESC")
        return [self._row_to_dict(row) for row in rows]

    def get_by_id(self, item_id: str) -> dict:
        """根据 ID 获取市场项"""
        row = self.db.query_one(f"SELECT * FROM {self.TABLE} WHERE id = ?", (item_id,))
        return self._row_to_dict(row) if row else {}

    def count(self) -> int:
        """获取市场项数量"""
        return self.db.query_value(f"SELECT COUNT(*) FROM {self.TABLE}") or 0

    # ==========================================
    # 写入
    # ==========================================

    def upsert(self, item: dict):
        """插入或更新市场项（保留已有 installed/tested 标记）"""
        data = self._normalize(item)
        item_id = data.get("id", "")

        # 若传入未指定 installed/tested（None），则保留数据库已有值
        if item_id:
            existing = self.get_by_id(item_id)
            if data.get("installed") is None and existing:
                data["installed"] = 1 if existing.get("installed") else 0
            if data.get("tested") is None and existing:
                data["tested"] = 1 if existing.get("tested") else 0
        else:
            # 无 id，使用默认值
            if data.get("installed") is None:
                data["installed"] = 0
            if data.get("tested") is None:
                data["tested"] = 0

        exists = self.db.query_one(
            f"SELECT id FROM {self.TABLE} WHERE id = ?", (item_id,)
        ) if item_id else None

        if exists:
            self.db.execute(
                f"UPDATE {self.TABLE} SET name=?, title=?, github_repo_url=?, logo=?, "
                f"description=?, author=?, issue_number=?, installed=?, tested=?, "
                f"server_type=?, labels=?, created_at=?, raw_issue=?, fetched_at=?, "
                f"server_id=? WHERE id=?",
                (data.get("name"), data.get("title"), data.get("github_repo_url"),
                 data.get("logo"), data.get("description"), data.get("author"),
                 data.get("issue_number"), data.get("installed"), data.get("tested"),
                 data.get("server_type"), data.get("labels"), data.get("created_at"),
                 data.get("raw_issue"), data.get("fetched_at"), data.get("server_id"),
                 item_id),
            )
        else:
            self.db.execute(
                f"INSERT INTO {self.TABLE} (id, name, title, github_repo_url, logo, "
                f"description, author, issue_number, installed, tested, server_type, "
                f"labels, created_at, raw_issue, fetched_at, server_id) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data.get("id"), data.get("name"), data.get("title"),
                 data.get("github_repo_url"), data.get("logo"), data.get("description"),
                 data.get("author"), data.get("issue_number"), data.get("installed"),
                 data.get("tested"), data.get("server_type"), data.get("labels"),
                 data.get("created_at"), data.get("raw_issue"), data.get("fetched_at"),
                 data.get("server_id")),
            )

    def upsert_many(self, items: list):
        """批量插入或更新"""
        for item in items:
            self.upsert(item)

    def set_installed(self, item_id: str, installed: bool):
        """设置安装状态"""
        self.db.execute(
            f"UPDATE {self.TABLE} SET installed = ? WHERE id = ?",
            (1 if installed else 0, item_id),
        )

    def set_server_id(self, item_id: str, server_id: str):
        """设置市场项对应的服务器 ID（mcp_servers.json 配置 key）"""
        self.db.execute(
            f"UPDATE {self.TABLE} SET server_id = ? WHERE id = ?",
            (server_id, item_id),
        )

    def clear(self):
        """清空所有市场数据"""
        self.db.execute(f"DELETE FROM {self.TABLE}")

    # ==========================================
    # 工具方法
    # ==========================================

    def _normalize(self, item: dict) -> Dict[str, Any]:
        """将前端字段名（camelCase）转为数据库字段名（snake_case），并序列化 JSON"""
        mapping = {
            "githubRepoUrl": "github_repo_url",
            "issueNumber": "issue_number",
            "installed": "installed",
            "tested": "tested",
            "serverType": "server_type",
            "createdAt": "created_at",
            "rawIssue": "raw_issue",
            "fetchedAt": "fetched_at",
            "serverId": "server_id",
        }
        table_fields = {
            "id", "name", "title", "github_repo_url", "logo", "description",
            "author", "issue_number", "installed", "tested", "server_type",
            "labels", "created_at", "raw_issue", "fetched_at", "server_id",
        }
        data = {}
        for k, v in item.items():
            db_key = mapping.get(k, k)
            if db_key not in table_fields:
                continue
            data[db_key] = v
        # 确保 installed/tested 为整数（None 保留，供 upsert 判断保留已有值）
        for f in ("installed", "tested"):
            if f in data and data[f] is not None:
                data[f] = 1 if data[f] else 0
        # JSON 字段序列化
        for f in ("labels", "raw_issue"):
            if data.get(f) is not None and not isinstance(data[f], str):
                data[f] = json.dumps(data[f], ensure_ascii=False)
        return data

    def _row_to_dict(self, row: dict) -> dict:
        """将数据库行转为前端期望的字段名格式（camelCase）+ JSON 反序列化"""
        # 反序列化 JSON 字段
        labels = row.get("labels")
        raw_issue = row.get("raw_issue")
        try:
            labels = json.loads(labels) if isinstance(labels, str) else (labels or [])
        except (ValueError, TypeError):
            labels = []
        try:
            raw_issue = json.loads(raw_issue) if isinstance(raw_issue, str) else (raw_issue or {})
        except (ValueError, TypeError):
            raw_issue = {}

        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "title": row.get("title"),
            "githubRepoUrl": row.get("github_repo_url"),
            "logo": row.get("logo"),
            "description": row.get("description"),
            "author": row.get("author"),
            "issueNumber": row.get("issue_number"),
            "installed": bool(row.get("installed")),
            "tested": bool(row.get("tested")),
            "serverType": row.get("server_type"),
            "labels": labels,
            "createdAt": row.get("created_at"),
            "raw_issue": raw_issue,
            "fetched_at": row.get("fetched_at"),
            "serverId": row.get("server_id"),
        }
