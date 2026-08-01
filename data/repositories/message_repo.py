"""
消息仓库
"""
from typing import List, Optional
from data.repositories.base_repository import BaseRepository
from model.entities.message import MessageModel


class MessageRepository(BaseRepository[MessageModel]):
    """消息数据仓库"""

    def __init__(self):
        super().__init__(MessageModel)

    def find_by_conversation(self, conversation_id: str) -> List[MessageModel]:
        """根据对话 ID 查找所有消息"""
        return self.find(conversation_id=conversation_id)