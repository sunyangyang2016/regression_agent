"""
对话模型
"""
from datetime import datetime
from typing import List, Optional
from model.entities.base import BaseModel


class ConversationModel(BaseModel):
    """对话模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title: str = kwargs.get("title", "新对话")
        self.user_id: str = kwargs.get("user_id", "")
        self.session_id: str = kwargs.get("session_id", "")
        self.model: str = kwargs.get("model", "deepseek-chat")
        self.message_count: int = kwargs.get("message_count", 0)
        self.token_count: int = kwargs.get("token_count", 0)
        self.status: str = kwargs.get("status", "active")  # active, archived, deleted
        self.tags: List[str] = kwargs.get("tags", [])