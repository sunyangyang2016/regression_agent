"""
网页抓取技能 - 网络信息采集
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class WebScraperSkill(BaseSkill):
    """网页抓取技能"""

    name = "web_scraper"
    description = "网页内容抓取、链接提取和结构化数据采集"
    category = "data"
    tags = ["web", "scraping", "crawler", "extraction"]
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的网页 URL"},
            "extract_type": {"type": "string", "description": "提取类型: content(正文), links(链接), images(图片), structured(结构化数据)", "enum": ["content", "links", "images", "structured"]},
            "selector": {"type": "string", "description": "CSS 选择器（可选），用于精确提取特定元素"},
        },
        "required": ["url"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        url = kwargs.get("url", context.get("url", ""))
        extract_type = kwargs.get("extract_type", context.get("extract_type", "content"))

        return SkillResult(
            success=True,
            output={
                "url": url,
                "extract_type": extract_type,
                "message": f"网页抓取请求：{url} (提取类型：{extract_type})",
            },
            metadata={"url": url, "extract_type": extract_type},
        )