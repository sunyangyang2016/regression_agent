"""
对话仓库
"""
from typing import List, Optional
from data.repositories.base_repository import BaseRepository
from model.entities.conversation import ConversationModel


class ConversationRepository(BaseRepository[ConversationModel]):
    """对话数据仓库"""

    def __init__(self):
        super().__init__(ConversationModel)

    def find_by_user(self, user_id: str) -> List[ConversationModel]:
        """根据用户 ID 查找对话"""
        return self.find(user_id=user_id)