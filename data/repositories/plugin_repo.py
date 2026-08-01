"""
插件仓库
"""
from typing import List, Optional
from data.repositories.base_repository import BaseRepository
from model.entities.base import BaseModel


class PluginModel(BaseModel):
    """插件模型"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name: str = kwargs.get("name", "")
        self.version: str = kwargs.get("version", "1.0.0")
        self.description: str = kwargs.get("description", "")
        self.enabled: bool = kwargs.get("enabled", True)
        self.source: str = kwargs.get("source", "builtin")


class PluginRepository(BaseRepository[PluginModel]):
    """插件数据仓库"""

    def __init__(self):
        super().__init__(PluginModel)

    def find_enabled(self) -> List[PluginModel]:
        return [p for p in self._data.values() if p.enabled]

    def find_by_name(self, name: str) -> Optional[PluginModel]:
        for p in self._data.values():
            if p.name == name:
                return p
        return None