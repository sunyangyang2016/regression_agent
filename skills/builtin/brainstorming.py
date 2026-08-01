"""
头脑风暴技能 - 创意生成和思维发散
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class BrainstormingSkill(BaseSkill):
    """头脑风暴技能"""

    name = "brainstorming"
    description = "创意生成、思维发散和方案策划辅助"
    category = "creativity"
    tags = ["brainstorm", "creativity", "idea", "innovation"]
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "头脑风暴的主题或问题"},
            "technique": {"type": "string", "description": "思维技术: free(自由联想), mindmap(思维导图), scamper(SCAMPER法), six_hats(六顶思考帽)", "enum": ["free", "mindmap", "scamper", "six_hats"]},
            "count": {"type": "integer", "description": "生成创意的数量（可选）"},
        },
        "required": ["topic"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        topic = kwargs.get("topic", context.get("topic", ""))
        technique = kwargs.get("technique", context.get("technique", "free"))

        return SkillResult(
            success=True,
            output={
                "topic": topic,
                "technique": technique,
                "message": f"头脑风暴请求：{topic}（方法：{technique}）",
            },
            metadata={"technique": technique},
        )