"""
MCP 服务器日志仓库 — 经典 Repository 模式
持有 db（Database 连接池），使用原生 SQL 访问 mcp_server_logs 表
返回业务实体 MCPServerLog
"""
from datetime import datetime
from typing import List, Optional

from storage.database import Database
from model.entities.mcp_server_log import MCPServerLog


class MCPServerLogsRepository:
    """MCP 服务器日志仓库（持有 db + 原生 SQL）"""

    TABLE = "mcp_server_logs"  # 表名

    def __init__(self):
        self.db = Database()  # 直接持有数据库（连接池）

    # ==========================================
    # CRUD
    # ==========================================

    def save(self, item: MCPServerLog) -> bool:
        """保存日志实体（Insert 或 Update）"""
        data = item.to_dict(for_db=True)
        # datetime → isoformat 字符串
        for k in ("created_at", "updated_at"):
            if isinstance(data.get(k), datetime):
                data[k] = data[k].isoformat()

        # 若无 id 自动生成，并回写实体
        if not data.get("id"):
            import uuid
            generated = str(uuid.uuid4())
            data["id"] = generated
            item.id = generated

        existing = self.db.query_one(
            f"SELECT id FROM {self.TABLE} WHERE id = ?", (data.get("id"),)
        )
        if existing:
            self.db.execute(
                f"UPDATE {self.TABLE} SET server_id=?, action=?, status=?, log_content=?, "
                f"log_file=?, duration=?, server_name=?, repo_url=?, market_id=?, updated_at=? WHERE id=?",
                (data.get("server_id"), data.get("action"), data.get("status"),
                 data.get("log_content"), data.get("log_file"), data.get("duration"),
                 data.get("server_name"), data.get("repo_url"), data.get("market_id"),
                 data.get("updated_at"), data.get("id")),
            )
        else:
            self.db.execute(
                f"INSERT INTO {self.TABLE} (id, server_id, action, status, log_content, "
                f"log_file, duration, server_name, repo_url, market_id, created_at, updated_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data.get("id"), data.get("server_id"), data.get("action"),
                 data.get("status"), data.get("log_content"), data.get("log_file"),
                 data.get("duration"), data.get("server_name"), data.get("repo_url"),
                 data.get("market_id"), data.get("created_at"), data.get("updated_at")),
            )
        return True

    def get(self, item_id: str) -> Optional[MCPServerLog]:
        """根据 ID 获取日志实体"""
        row = self.db.query_one(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (item_id,)
        )
        return MCPServerLog.from_dict(row) if row else None

    def get_all(self) -> List[MCPServerLog]:
        """获取所有日志"""
        rows = self.db.query(f"SELECT * FROM {self.TABLE}")
        return [MCPServerLog.from_dict(r) for r in rows]

    def delete(self, item_id: str) -> bool:
        """删除日志"""
        self.db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (item_id,))
        return True

    def delete_by_server(self, server_id: str) -> int:
        """删除某服务器的全部日志"""
        return self.db.execute(
            f"DELETE FROM {self.TABLE} WHERE server_id = ?", (server_id,)
        )

    # ==========================================
    # 便捷方法
    # ==========================================

    def get_by_server(self, server_id: str, order_by: str = "created_at DESC") -> List[MCPServerLog]:
        """按服务器 ID 查询日志"""
        rows = self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE server_id = ? ORDER BY {order_by}",
            (server_id,),
        )
        return [MCPServerLog.from_dict(r) for r in rows]

    def get_by_action(self, action: str) -> List[MCPServerLog]:
        """按操作类型查询"""
        rows = self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE action = ? ORDER BY created_at DESC",
            (action,),
        )
        return [MCPServerLog.from_dict(r) for r in rows]

    def get_by_market(self, market_id: str, order_by: str = "created_at DESC") -> List[MCPServerLog]:
        """按市场项 ID 查询日志（市场安装的服务器）"""
        rows = self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE market_id = ? ORDER BY {order_by}",
            (market_id,),
        )
        return [MCPServerLog.from_dict(r) for r in rows]

    def count(self, server_id: Optional[str] = None, market_id: Optional[str] = None) -> int:
        """日志数量（可按服务器或市场项筛选）"""
        if server_id:
            return self.db.query_value(
                f"SELECT COUNT(*) FROM {self.TABLE} WHERE server_id = ?", (server_id,)
            ) or 0
        if market_id:
            return self.db.query_value(
                f"SELECT COUNT(*) FROM {self.TABLE} WHERE market_id = ?", (market_id,)
            ) or 0
        return self.db.query_value(f"SELECT COUNT(*) FROM {self.TABLE}") or 0

    def clear(self):
        """清空日志表"""
        self.db.execute(f"DELETE FROM {self.TABLE}")