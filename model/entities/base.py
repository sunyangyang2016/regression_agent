"""
实体基类 — 业务纯数据对象
不含数据库逻辑，仅定义业务字段和序列化能力
"""
from datetime import datetime


class BaseEntity:
    """业务实体基类"""

    # 读取数据库时需从字符串还原为 datetime 的字段
    datetime_fields = ("created_at", "updated_at")

    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id", "")
        self.created_at = kwargs.get("created_at")
        self.updated_at = kwargs.get("updated_at")

    def to_dict(self) -> dict:
        """实体转字典（datetime → isoformat 字符串）"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif value is None:
                result[key] = None
            else:
                result[key] = value
        return result

    def to_json(self, indent: int = None) -> str:
        """实体转 JSON 字符串"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "BaseEntity":
        """字典转实体

        自动将 datetime_fields 中的字符串（数据库读取）还原为 datetime 对象，
        以便业务层可以直接调用 .isoformat() 等方法。
        """
        data = dict(data)
        for field in cls.datetime_fields:
            val = data.get(field)
            if isinstance(val, str):
                try:
                    data[field] = datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    pass
        return cls(**data)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"