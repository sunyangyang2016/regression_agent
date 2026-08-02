"""
MdSkill - Markdown 技能适配器
将 Markdown 技能目录（skills/md/<name>/SKILL.md）包装为可执行的 BaseSkill，
使 MD 技能也能通过 SkillDispatcher 被 tool-call 执行，实现统一技能模型。

目录结构：
  <skill-name>/
    SKILL.md          # 必需：核心指令与元数据
    scripts/          # 可选：可执行的脚本（.py, .sh）
    references/       # 可选：供 AI 参考的详细文档
    assets/           # 可选：模板、图片等静态资源
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
        self._skill_dir = skill_dict.get("skill_dir", "")
        self._scripts = skill_dict.get("scripts", [])
        self._references = skill_dict.get("references", [])
        self._assets = skill_dict.get("assets", [])
        self._skill_dict = skill_dict
        super().__init__()

    @property
    def skill_dir(self) -> str:
        """技能目录完整路径"""
        return self._skill_dir

    @property
    def scripts(self) -> list:
        """可用脚本相对路径列表"""
        return list(self._scripts)

    @property
    def references(self) -> list:
        """参考文档相对路径列表"""
        return list(self._references)

    @property
    def assets(self) -> list:
        """附加资源相对路径列表"""
        return list(self._assets)

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """返回 MD 技能内容（作为提示词/上下文供 AI 参考）"""
        output = self._content
        try:
            from skills.loader import SkillLoader
            loader = SkillLoader()
            output = loader._expand_skill_content_paths(self._skill_dict, self._content)
        except Exception:
            pass
        return SkillResult(
            success=True,
            output=output,
            metadata={
                "source": "markdown",
                "name": self.name,
                "filepath": self._filepath,
                "skill_dir": self._skill_dir,
                "scripts": list(self._scripts),
                "references": list(self._references),
                "assets": list(self._assets),
            },
        )

    def get_metadata(self) -> Dict[str, Any]:
        data = super().get_metadata()
        data["source"] = "markdown"
        data["filepath"] = self._filepath
        data["skill_dir"] = self._skill_dir
        data["scripts"] = list(self._scripts)
        data["references"] = list(self._references)
        data["assets"] = list(self._assets)
        return data


def skill_dict_to_skill(skill_dict: Dict[str, Any]) -> Optional[MdSkill]:
    """将解析后的 MD 技能 dict 转为 MdSkill 实例（名称缺失时返回 None）"""
    if not skill_dict or not skill_dict.get("name"):
        return None
    return MdSkill(skill_dict)