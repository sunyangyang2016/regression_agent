"""
MdSkill - Markdown 技能适配器
将 Markdown 技能文件（skills/md/*.md）包装为可执行的 BaseSkill，
使 MD 技能也能通过 SkillDispatcher 被 tool-call 执行，实现统一技能模型。
"""
from typing import Any, Dict, Optional

from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class MdSkill(BaseSkill):
    """MD 技能适配器 - 将解析后的 MD 技能 dict 包装为 BaseSkill"""

    def __init__(self, skill_dict: Dict[str, Any]):
        self.name = skill_dict.get("name", "") or "unnamed"
        self.description = skill_dict.get("description", "") or f"Markdown 技能：{self.name}"
        self.category = "md"
        self._content = skill_dict.get("content", "")
        self._filepath = skill_dict.get("filepath", "")
        self._skill_dict = skill_dict
        super().__init__()

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """返回 MD 技能内容（作为提示词/上下文供 AI 参考）"""
        return SkillResult(
            success=True,
            output=self._content,
            metadata={
                "source": "markdown",
                "name": self.name,
                "filepath": self._filepath,
            },
        )

    def get_metadata(self) -> Dict[str, Any]:
        data = super().get_metadata()
        data["source"] = "markdown"
        data["filepath"] = self._filepath
        return data


def skill_dict_to_skill(skill_dict: Dict[str, Any]) -> Optional[MdSkill]:
    """将解析后的 MD 技能 dict 转为 MdSkill 实例（名称缺失时返回 None）"""
    if not skill_dict or not skill_dict.get("name"):
        return None
    return MdSkill(skill_dict)
