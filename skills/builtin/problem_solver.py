"""
问题求解技能 - 系统性问题分析和解决
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class ProblemSolverSkill(BaseSkill):
    """问题求解技能"""

    name = "problem_solver"
    description = "系统性问题分析、根因分析和解决方案设计"
    category = "analysis"
    tags = ["problem", "solving", "analysis", "root-cause"]
    input_schema = {
        "type": "object",
        "properties": {
            "problem": {"type": "string", "description": "需要解决的问题描述"},
            "method": {"type": "string", "description": "分析方法: root_cause(根因分析), swot(SWOT分析), first_principles(第一性原理), five_whys(5WHY法)", "enum": ["root_cause", "swot", "first_principles", "five_whys"]},
            "context": {"type": "string", "description": "问题背景信息（可选）"},
        },
        "required": ["problem"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        problem = kwargs.get("problem", context.get("problem", ""))
        method = kwargs.get("method", context.get("method", "root_cause"))

        return SkillResult(
            success=True,
            output={
                "problem": problem,
                "method": method,
                "message": f"问题求解请求：{problem}（方法：{method}）",
            },
            metadata={"method": method},
        )