"""
会议纪要技能 - 会议记录和要点整理
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class MeetingMinutesSkill(BaseSkill):
    """会议纪要技能"""

    name = "meeting_minutes"
    description = "会议记录整理、要点提取和行动项生成"
    category = "productivity"
    tags = ["meeting", "minutes", "notes", "productivity"]
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "会议记录或讨论内容"},
            "format": {"type": "string", "description": "输出格式: structured(结构化), mindmap(思维导图), summary(摘要)", "enum": ["structured", "mindmap", "summary"]},
            "include_action_items": {"type": "boolean", "description": "是否提取行动项"},
        },
        "required": ["content"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        content = kwargs.get("content", context.get("content", ""))
        format_type = kwargs.get("format", context.get("format", "structured"))

        return SkillResult(
            success=True,
            output={
                "content_length": len(content),
                "format": format_type,
                "message": f"会议纪要整理请求：{len(content)} 字符（格式：{format_type}）",
            },
            metadata={"format": format_type},
        )