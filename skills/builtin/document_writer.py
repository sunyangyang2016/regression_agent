"""
文档写作技能 - 辅助技术文档和文章撰写
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class DocumentWriterSkill(BaseSkill):
    """文档写作技能"""

    name = "document_writer"
    description = "辅助技术文档、文章和报告撰写"
    category = "writing"
    tags = ["writing", "documentation", "article", "report"]
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "文档主题或标题"},
            "doc_type": {"type": "string", "description": "文档类型: technical(技术文档), api(API文档), tutorial(教程), report(报告), article(文章)",
                         "enum": ["technical", "api", "tutorial", "report", "article"]},
            "style": {"type": "string", "description": "写作风格: formal(正式), casual(轻松), academic(学术)"},
            "outline": {"type": "string", "description": "大纲要点（可选）"},
        },
        "required": ["topic"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        topic = kwargs.get("topic", context.get("topic", ""))
        doc_type = kwargs.get("doc_type", context.get("doc_type", "technical"))
        style = kwargs.get("style", context.get("style", "formal"))

        return SkillResult(
            success=True,
            output={
                "topic": topic,
                "doc_type": doc_type,
                "style": style,
                "message": f"已准备撰写 '{doc_type}' 类型文档：{topic}",
            },
            metadata={"doc_type": doc_type, "style": style},
        )