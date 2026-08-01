"""
工具模型
"""
from typing import Dict, Any, Optional
from model.entities.base import BaseModel


class ToolModel(BaseModel):
    """工具模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name: str = kwargs.get("name", "")
        self.description: str = kwargs.get("description", "")
        self.version: str = kwargs.get("version", "1.0.0")
        self.category: str = kwargs.get("category", "builtin")
        self.enabled: bool = kwargs.get("enabled", True)
        self.config: Dict[str, Any] = kwargs.get("config", {})
        self.input_schema: dict = kwargs.get("input_schema", {})