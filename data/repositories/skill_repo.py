"""
技能仓库
"""
from typing import List, Optional
from data.repositories.base_repository import BaseRepository
from model.entities.skill import SkillModel


class SkillRepository(BaseRepository[SkillModel]):
    """技能数据仓库"""

    def __init__(self):
        super().__init__(SkillModel)

    def find_enabled(self) -> List[SkillModel]:
        """查找已启用的技能"""
        return [s for s in self._data.values() if s.enabled]

    def find_by_category(self, category: str) -> List[SkillModel]:
        """根据类别查找技能"""
        return [s for s in self._data.values() if s.category == category]

    def find_by_name(self, name: str) -> Optional[SkillModel]:
        """根据名称查找技能"""
        for s in self._data.values():
            if s.name == name:
                return s
        return None

    def find_by_source(self, source: str) -> List[SkillModel]:
        """根据来源查找技能"""
        return [s for s in self._data.values() if s.source == source]