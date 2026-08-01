"""
会话模型
"""
from datetime import datetime
from typing import Optional
from model.entities.base import BaseModel


class SessionModel(BaseModel):
    """会话模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_id: str = kwargs.get("user_id", "")
        self.active_conversation_id: Optional[str] = kwargs.get("active_conversation_id")
        self.status: str = kwargs.get("status", "active")  # active, expired, closed
        self.expires_at: Optional[datetime] = kwargs.get("expires_at")
        self.metadata: dict = kwargs.get("metadata", {})