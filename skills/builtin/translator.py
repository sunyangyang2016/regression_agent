"""
翻译技能 - 多语言翻译功能
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class TranslatorSkill(BaseSkill):
    """翻译技能"""

    name = "translator"
    description = "多语言翻译，支持文本翻译和语言检测"
    category = "utility"
    tags = ["translate", "language", "i18n"]
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要翻译的文本内容"},
            "target_lang": {"type": "string", "description": "目标语言代码，如 zh(中文), en(英文), ja(日文), fr(法文), de(德文), es(西文)"},
            "source_lang": {"type": "string", "description": "源语言代码（可选），auto 表示自动检测"},
        },
        "required": ["text", "target_lang"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        text = kwargs.get("text", context.get("text", ""))
        target_lang = kwargs.get("target_lang", context.get("target_lang", "zh"))
        source_lang = kwargs.get("source_lang", context.get("source_lang", "auto"))

        return SkillResult(
            success=True,
            output={
                "text_length": len(text),
                "source_lang": source_lang,
                "target_lang": target_lang,
                "message": f"翻译请求：{source_lang} → {target_lang} ({len(text)} 字符)",
            },
            metadata={"source_lang": source_lang, "target_lang": target_lang},
        )