"""
代码助手技能 - 协助代码审查、优化和调试
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class CodeAssistantSkill(BaseSkill):
    """代码助手技能"""

    name = "code_assistant"
    description = "代码审查、优化和调试助手"
    category = "development"
    tags = ["code", "review", "debug", "optimization"]
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要审查或优化的代码内容"},
            "action": {"type": "string", "description": "操作类型: review(审查), optimize(优化), debug(调试), refactor(重构)", "enum": ["review", "optimize", "debug", "refactor"]},
            "language": {"type": "string", "description": "编程语言 (如 python, javascript, typescript, go 等)"},
        },
        "required": ["code"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        code = kwargs.get("code", context.get("code", ""))
        action = kwargs.get("action", "review")
        language = kwargs.get("language", context.get("language", "python"))

        return SkillResult(
            success=True,
            output={
                "action": action,
                "language": language,
                "code_length": len(code),
                "message": f"代码助手 '{action}' 已处理 {len(code)} 字符的 {language} 代码",
            },
            metadata={"action": action, "language": language},
        )