"""
会话仓库 — 经典 Repository 模式
持有 db（Database 连接池），使用原生 SQL 访问 history_sessions_index 表
返回业务实体 ChatSession
"""
from datetime import datetime
from typing import List, Optional

from storage.database import Database
from model.entities.chat_session import ChatSession


class ConversationRepository:
    """会话数据仓库（持有 db + 原生 SQL）"""

    TABLE = "history_sessions_index"  # 表名

    def __init__(self):
        self.db = Database()  # 直接持有数据库（连接池）

    # ==========================================
    # CRUD
    # ==========================================

    def save(self, item: ChatSession) -> bool:
        """保存会话实体（Insert 或 Update）"""
        data = item.to_dict(for_db=True)
        # datetime → isoformat 字符串
        for k in ("created_at", "updated_at"):
            if isinstance(data.get(k), datetime):
                data[k] = data[k].isoformat()

        existing = self.db.query_one(
            f"SELECT id FROM {self.TABLE} WHERE id = ?", (data.get("id"),)
        )
        if existing:
            self.db.execute(
                f"UPDATE {self.TABLE} SET title=?, model=?, message_count=?, token_count=?, hit_token_count=?, miss_token_count=?, output_token_count=?, status=?, updated_at=?, log_file=? WHERE id=?",
                (data.get("title"), data.get("model"), data.get("message_count"),
                 data.get("token_count"), data.get("hit_token_count"), data.get("miss_token_count"),
                 data.get("output_token_count"), data.get("status"), data.get("updated_at"),
                 data.get("log_file"), data.get("id")),
            )
        else:
            # 若无 id 自动生成，并回写到实体对象（业务层可直接取用）
            if not data.get("id"):
                import uuid
                generated = str(uuid.uuid4())
                data["id"] = generated
                item.id = generated  # 回写
            self.db.execute(
                f"INSERT INTO {self.TABLE} (id, title, model, message_count, token_count, hit_token_count, miss_token_count, output_token_count, status, created_at, updated_at, log_file) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data.get("id"), data.get("title"), data.get("model"),
                 data.get("message_count"), data.get("token_count"),
                 data.get("hit_token_count"), data.get("miss_token_count"), data.get("output_token_count"),
                 data.get("status"),
                 data.get("created_at"), data.get("updated_at"), data.get("log_file")),
            )
        return True

    def get(self, item_id: str) -> Optional[ChatSession]:
        """根据 ID 获取会话实体"""
        row = self.db.query_one(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (item_id,)
        )
        return ChatSession.from_dict(row) if row else None

    def get_all(self) -> List[ChatSession]:
        """获取所有会话实体"""
        rows = self.db.query(f"SELECT * FROM {self.TABLE}")
        return [ChatSession.from_dict(r) for r in rows]

    def delete(self, item_id: str) -> bool:
        """删除会话"""
        self.db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (item_id,))
        return True

    # ==========================================
    # 便捷方法
    # ==========================================

    def find(self, **filters) -> List[ChatSession]:
        """按条件查找"""
        rows = self.db.query(f"SELECT * FROM {self.TABLE}")
        results = []
        for r in rows:
            match = True
            for k, v in filters.items():
                if r.get(k) != v:
                    match = False
                    break
            if match:
                results.append(ChatSession.from_dict(r))
        return results

    def find_by_user(self, user_id: str) -> List[ChatSession]:
        """根据用户 ID 查找（当前无用户字段，返回全部）"""
        return self.get_all()

    def count(self) -> int:
        """会话数量"""
        return self.db.query_value(f"SELECT COUNT(*) FROM {self.TABLE}") or 0

    def clear(self):
        """清空会话表"""
        self.db.execute(f"DELETE FROM {self.TABLE}")