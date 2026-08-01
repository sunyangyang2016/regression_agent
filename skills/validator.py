"""
技能验证器 - 验证技能的配置和执行合法性
"""
from typing import List, Optional, Tuple
from skills.base import BaseSkill


class SkillValidator:
    """技能验证器"""

    @staticmethod
    def validate_skill(skill: BaseSkill) -> Tuple[bool, List[str]]:
        """验证单个技能是否合法"""
        errors = []

        if not skill.name:
            errors.append("技能名称不能为空")
        elif len(skill.name) > 128:
            errors.append("技能名称长度不能超过 128 个字符")

        if not skill.description and not hasattr(type(skill), "execute"):
            errors.append("技能缺少描述")

        if not skill.validate():
            errors.append("技能基类验证失败")

        return len(errors) == 0, errors

    @staticmethod
    def validate_execution_params(
        skill: BaseSkill,
        **kwargs
    ) -> Tuple[bool, List[str]]:
        """验证执行参数"""
        errors = []

        if not skill.enabled:
            errors.append(f"技能 '{skill.name}' 当前已禁用")

        return len(errors) == 0, errors

    @staticmethod
    def validate_name(name: str) -> Tuple[bool, Optional[str]]:
        """验证技能名称格式"""
        if not name or not name.strip():
            return False, "技能名称不能为空"
        if len(name) > 128:
            return False, "技能名称长度不能超过 128 个字符"
        if not name.replace("_", "").replace("-", "").isalnum():
            return False, "技能名称只能包含字母、数字、下划线和连字符"
        return True, None