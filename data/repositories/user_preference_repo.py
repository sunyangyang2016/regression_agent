"""
用户偏好仓库
"""
from typing import Dict, Any, Optional
from data.repositories.base_repository import BaseRepository
from model.entities.base import BaseModel


class UserPreferenceModel(BaseModel):
    """用户偏好模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_id: str = kwargs.get("user_id", "")
        self.theme: str = kwargs.get("theme", "default")
        self.language: str = kwargs.get("language", "zh")
        self.notifications_enabled: bool = kwargs.get("notifications_enabled", True)
        self.settings: Dict[str, Any] = kwargs.get("settings", {})


class UserPreferenceRepository(BaseRepository[UserPreferenceModel]):
    """用户偏好数据仓库"""

    def __init__(self):
        super().__init__(UserPreferenceModel)

    def find_by_user(self, user_id: str) -> Optional[UserPreferenceModel]:
        for p in self._data.values():
            if p.user_id == user_id:
                return p
        return None

    def upsert(self, user_id: str, data: Dict[str, Any]) -> UserPreferenceModel:
        pref = self.find_by_user(user_id)
        if pref:
            pref.update(**data)
            return pref
        new_pref = UserPreferenceModel(user_id=user_id, **data)
        self.save(new_pref)
        return new_pref