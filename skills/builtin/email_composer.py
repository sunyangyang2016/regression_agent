"""
邮件撰写技能 - 辅助邮件内容撰写和模板管理
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class EmailComposerSkill(BaseSkill):
    """邮件撰写技能"""

    name = "email_composer"
    description = "辅助邮件撰写、模板管理和邮件内容优化"
    category = "communication"
    tags = ["email", "communication", "template"]
    input_schema = {
        "type": "object",
        "properties": {
            "purpose": {"type": "string", "description": "邮件目的描述"},
            "recipient": {"type": "string", "description": "收件人信息（可选）"},
            "tone": {"type": "string", "description": "语气风格: formal(正式), friendly(友好), professional(专业)", "enum": ["formal", "friendly", "professional"]},
            "key_points": {"type": "string", "description": "邮件要点（可选，逗号分隔）"},
        },
        "required": ["purpose"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        purpose = kwargs.get("purpose", context.get("purpose", ""))
        recipient = kwargs.get("recipient", context.get("recipient", ""))
        tone = kwargs.get("tone", context.get("tone", "formal"))

        return SkillResult(
            success=True,
            output={
                "purpose": purpose,
                "recipient": recipient,
                "tone": tone,
                "message": f"邮件撰写请求：{purpose}（语气：{tone}）",
            },
            metadata={"tone": tone},
        )