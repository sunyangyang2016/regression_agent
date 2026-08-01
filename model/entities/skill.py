"""
技能模型
"""
from typing import Dict, Any, List, Optional
from model.entities.base import BaseModel


class SkillModel(BaseModel):
    """技能模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name: str = kwargs.get("name", "")
        self.description: str = kwargs.get("description", "")
        self.version: str = kwargs.get("version", "1.0.0")
        self.category: str = kwargs.get("category", "general")
        self.enabled: bool = kwargs.get("enabled", True)
        self.tags: List[str] = kwargs.get("tags", [])
        self.source: str = kwargs.get("source", "builtin")
        self.source_path: Optional[str] = kwargs.get("source_path")
        self.config: Dict[str, Any] = kwargs.get("config", {})