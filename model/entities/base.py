"""
基础数据模型
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class BaseModel:
    """数据模型基类"""

    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id", str(uuid.uuid4()))
        self.created_at: datetime = kwargs.get("created_at", datetime.now())
        self.updated_at: datetime = kwargs.get("updated_at", datetime.now())

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

    def to_json(self) -> str:
        """转为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseModel":
        """从字典创建实例"""
        return cls(**data)

    def update(self, **kwargs):
        """更新字段"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"