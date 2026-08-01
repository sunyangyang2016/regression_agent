"""
摘要生成技能 - 文本内容摘要提取
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class SummarizerSkill(BaseSkill):
    """摘要生成技能"""

    name = "summarizer"
    description = "文本摘要提取和关键信息归纳"
    category = "utility"
    tags = ["summary", "extraction", "key-points"]
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "需要生成摘要的文本内容"},
            "max_length": {"type": "integer", "description": "摘要最大字符数（可选）"},
            "style": {"type": "string", "description": "摘要风格: concise(简洁), detailed(详细), bullet(要点)", "enum": ["concise", "detailed", "bullet"]},
        },
        "required": ["text"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        text = kwargs.get("text", context.get("text", ""))
        max_length = kwargs.get("max_length", context.get("max_length", 200))
        style = kwargs.get("style", context.get("style", "concise"))

        return SkillResult(
            success=True,
            output={
                "original_length": len(text),
                "max_summary_length": max_length,
                "style": style,
                "message": f"摘要生成请求：{len(text)} 字符 → 最多 {max_length} 字 ({style})",
            },
            metadata={"max_length": max_length, "style": style},
        )