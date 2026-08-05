"""
消息实体 — ChatMessage
对应数据库表 history_sessions_messages 的业务对象
"""
from typing import Any, Dict, List, Optional

from model.entities.base import BaseEntity


class ChatMessage(BaseEntity):
    """消息实体"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session_id: str = kwargs.get("session_id", "")
        self.role: str = kwargs.get("role", "user")  # user, assistant, system, tool
        self.content: str = kwargs.get("content", "")
        self.tool_calls: list = kwargs.get("tool_calls", [])
        self.token_count: int = kwargs.get("token_count", 0)
        self.round_no: int = kwargs.get("round_no")      # AI 轮次序号（非轮次记录为 None）
        self.marker: str = kwargs.get("marker")          # 标记：tool_call / final（非轮次记录为 None）

    def to_dict(self, for_db: bool = False) -> dict:
        """转 dict（可选：仅含数据库字段）"""
        data = super().to_dict()
        if for_db:
            # 仅保留 history_sessions_messages 表字段
            return {
                "id": data.get("id"),
                "session_id": data.get("session_id"),
                "role": data.get("role"),
                "content": data.get("content"),
                "tool_calls": data.get("tool_calls"),
                "token_count": data.get("token_count"),
                "round_no": data.get("round_no"),
                "marker": data.get("marker"),
                "created_at": data.get("created_at"),
            }
        return data