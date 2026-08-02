"""
会话实体 — ChatSession
对应数据库表 history_sessions_index 的业务对象
"""
from datetime import datetime
from typing import Optional

from model.entities.base import BaseEntity


class ChatSession(BaseEntity):
    """会话实体"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title: str = kwargs.get("title", "新对话")
        self.model: str = kwargs.get("model", "")
        self.message_count: int = kwargs.get("message_count", 0)
        self.token_count: int = kwargs.get("token_count", 0)
        self.hit_token_count: int = kwargs.get("hit_token_count", 0)
        self.miss_token_count: int = kwargs.get("miss_token_count", 0)
        self.output_token_count: int = kwargs.get("output_token_count", 0)
        self.status: str = kwargs.get("status", "active")
        # AI 通信日志文件路径（logs/history 下的 JSON 文件）
        self.log_file: Optional[str] = kwargs.get("log_file") or None

    def to_dict(self, for_db: bool = False) -> dict:
        """转 dict（可选：仅含数据库字段）"""
        data = super().to_dict()
        if for_db:
            # 仅保留 history_sessions_index 表字段
            return {
                "id": data.get("id"),
                "title": data.get("title"),
                "model": data.get("model"),
                "message_count": data.get("message_count"),
                "token_count": data.get("token_count"),
                "hit_token_count": data.get("hit_token_count") or 0,
                "miss_token_count": data.get("miss_token_count") or 0,
                "output_token_count": data.get("output_token_count") or 0,
                "status": data.get("status"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "log_file": data.get("log_file") or None,
            }
        return data
