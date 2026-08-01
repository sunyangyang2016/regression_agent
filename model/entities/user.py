"""
用户模型
"""
from typing import Dict, Any, List, Optional
from model.entities.base import BaseModel


class UserModel(BaseModel):
    """用户模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.username: str = kwargs.get("username", "")
        self.email: str = kwargs.get("email", "")
        self.role: str = kwargs.get("role", "user")
        self.preferences: Dict[str, Any] = kwargs.get("preferences", {})
        self.api_keys: Dict[str, str] = kwargs.get("api_keys", {})
        self.active: bool = kwargs.get("active", True)