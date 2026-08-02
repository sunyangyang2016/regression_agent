"""
消息仓库 — 经典 Repository 模式
持有 db（Database 连接池），使用原生 SQL 访问 history_sessions_messages 表
返回业务实体 ChatMessage
"""
from datetime import datetime
from typing import List, Optional

from storage.database import Database
from model.entities.chat_message import ChatMessage


class MessageRepository:
    """消息数据仓库（持有 db + 原生 SQL）"""

    TABLE = "history_sessions_messages"  # 表名

    def __init__(self):
        self.db = Database()  # 直接持有数据库（连接池）

    # ==========================================
    # 类型转换
    # ==========================================

    @staticmethod
    def _serialize_dates(data: dict) -> dict:
        """datetime → isoformat 字符串"""
        for k, v in list(data.items()):
            if isinstance(v, datetime):
                data[k] = v.isoformat()
        return data

    # ==========================================
    # CRUD
    # ==========================================

    def save(self, item: ChatMessage) -> bool:
        """保存消息实体（Insert 或 Update）"""
        data = item.to_dict(for_db=False)
        # 序列化 datetime
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        # tool_calls 无条件转 JSON 字符串（即使是空列表也要存 '[]'）
        if not isinstance(data.get("tool_calls"), str):
            import json
            data["tool_calls"] = json.dumps(data.get("tool_calls") or [], ensure_ascii=False)

        # 若无 id 自动生成，并回写到实体对象（业务层可直接取用）
        if not data.get("id"):
            import uuid
            generated = str(uuid.uuid4())
            data["id"] = generated
            item.id = generated  # 回写

        existing = self.db.query_one(
            f"SELECT id FROM {self.TABLE} WHERE id = ?", (data.get("id"),)
        )
        if existing:
            self.db.execute(
                f"UPDATE {self.TABLE} SET session_id=?, role=?, content=?, tool_calls=?, token_count=? WHERE id=?",
                (data.get("session_id"), data.get("role"), data.get("content"),
                 data.get("tool_calls"), data.get("token_count"), data.get("id")),
            )
        else:
            self.db.execute(
                f"INSERT INTO {self.TABLE} (id, session_id, role, content, tool_calls, token_count, created_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data.get("id"), data.get("session_id"), data.get("role"),
                 data.get("content"), data.get("tool_calls"), data.get("token_count"),
                 data.get("created_at")),
            )
        return True

    @staticmethod
    def _deserialize(row: dict) -> dict:
        """读取时：tool_calls JSON 字符串 → list"""
        if isinstance(row.get("tool_calls"), str):
            import json
            try:
                row = dict(row)
                row["tool_calls"] = json.loads(row["tool_calls"])
            except (ValueError, TypeError):
                row = dict(row)
                row["tool_calls"] = []
        return row

    def get(self, item_id: str) -> Optional[ChatMessage]:
        """根据 ID 获取消息实体"""
        row = self.db.query_one(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (item_id,)
        )
        return ChatMessage.from_dict(self._deserialize(row)) if row else None

    def get_all(self) -> List[ChatMessage]:
        """获取所有消息实体"""
        rows = self.db.query(f"SELECT * FROM {self.TABLE}")
        return [ChatMessage.from_dict(self._deserialize(r)) for r in rows]

    def delete(self, item_id: str) -> bool:
        """删除消息"""
        self.db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (item_id,))
        return True

    def delete_by_session(self, session_id: str) -> int:
        """删除某会话的全部消息"""
        return self.db.execute(
            f"DELETE FROM {self.TABLE} WHERE session_id = ?", (session_id,)
        )

    # ==========================================
    # 便捷方法
    # ==========================================

    def get_by_session(self, session_id: str, order_by: str = "created_at ASC") -> List[ChatMessage]:
        """按会话 ID 查询消息"""
        rows = self.db.query(
            f"SELECT * FROM {self.TABLE} WHERE session_id = ? ORDER BY {order_by}",
            (session_id,),
        )
        return [ChatMessage.from_dict(self._deserialize(r)) for r in rows]

    def find_by_conversation(self, conversation_id: str) -> List[ChatMessage]:
        """按会话 ID 查找所有消息（兼容旧名，同 get_by_session）"""
        return self.get_by_session(conversation_id)

    def count_by_session(self, session_id: str) -> int:
        """统计某会话的消息数"""
        return self.db.query_value(
            f"SELECT COUNT(*) FROM {self.TABLE} WHERE session_id = ?", (session_id,)
        ) or 0

    def count(self) -> int:
        """消息总数"""
        return self.db.query_value(f"SELECT COUNT(*) FROM {self.TABLE}") or 0

    def find(self, **filters) -> List[ChatMessage]:
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
                results.append(ChatMessage.from_dict(self._deserialize(r)))
        return results

    def clear(self):
        """清空消息表"""
        self.db.execute(f"DELETE FROM {self.TABLE}")