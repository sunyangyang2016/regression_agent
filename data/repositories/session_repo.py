"""
会话仓库
"""
from typing import List, Optional
from datetime import datetime
from data.repositories.base_repository import BaseRepository
from model.entities.session import SessionModel


class SessionRepository(BaseRepository[SessionModel]):
    """会话数据仓库"""

    def __init__(self):
        super().__init__(SessionModel)

    def find_by_user(self, user_id: str) -> List[SessionModel]:
        """根据用户 ID 查找会话"""
        return [s for s in self._data.values() if s.user_id == user_id]

    def find_active(self) -> List[SessionModel]:
        """查找所有活跃会话"""
        return [s for s in self._data.values() if s.status == "active"]

    def find_expired(self) -> List[SessionModel]:
        """查找所有过期会话"""
        now = datetime.now()
        return [s for s in self._data.values() if s.expires_at and s.expires_at < now]

    def close(self, session_id: str) -> bool:
        """关闭会话"""
        session = self.get(session_id)
        if session:
            session.status = "closed"
            return True
        return False