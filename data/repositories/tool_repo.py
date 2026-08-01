"""
工具仓库
"""
from typing import List, Optional
from data.repositories.base_repository import BaseRepository
from model.entities.tool import ToolModel


class ToolRepository(BaseRepository[ToolModel]):
    """工具数据仓库"""

    def __init__(self):
        super().__init__(ToolModel)

    def find_enabled(self) -> List[ToolModel]:
        """查找所有已启用的工具"""
        return [t for t in self._data.values() if t.enabled]

    def find_by_category(self, category: str) -> List[ToolModel]:
        """根据类别查找工具"""
        return [t for t in self._data.values() if t.category == category]

    def find_by_name(self, name: str) -> Optional[ToolModel]:
        """根据名称查找工具"""
        for t in self._data.values():
            if t.name == name:
                return t
        return None