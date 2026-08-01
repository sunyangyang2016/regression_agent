"""
消息模型
"""
from typing import Dict, Any, Optional
from model.entities.base import BaseModel


class MessageModel(BaseModel):
    """消息模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conversation_id: str = kwargs.get("conversation_id", "")
        self.role: str = kwargs.get("role", "user")  # user, assistant, system, tool
        self.content: str = kwargs.get("content", "")
        self.tool_calls: list = kwargs.get("tool_calls", [])
        self.tool_call_id: Optional[str] = kwargs.get("tool_call_id")
        self.token_count: int = kwargs.get("token_count", 0)
        self.metadata: Dict[str, Any] = kwargs.get("metadata", {})