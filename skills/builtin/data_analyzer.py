"""
数据分析技能 - 协助数据分析和可视化
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class DataAnalyzerSkill(BaseSkill):
    """数据分析技能"""

    name = "data_analyzer"
    description = "协助数据分析、统计和可视化"
    category = "data"
    tags = ["data", "analysis", "statistics", "visualization"]
    input_schema = {
        "type": "object",
        "properties": {
            "data_source": {"type": "string", "description": "数据来源描述，如文件路径、数据库表名或数据描述"},
            "analysis_type": {"type": "string", "description": "分析类型: exploratory(探索性分析), statistical(统计分析), visualization(可视化), correlation(相关性)", "enum": ["exploratory", "statistical", "visualization", "correlation"]},
            "columns": {"type": "string", "description": "要分析的列名（可选，逗号分隔）"},
        },
        "required": ["data_source"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        data_source = kwargs.get("data_source", context.get("data_source", ""))
        analysis_type = kwargs.get("analysis_type", context.get("analysis_type", "exploratory"))

        return SkillResult(
            success=True,
            output={
                "data_source": data_source,
                "analysis_type": analysis_type,
                "message": f"已启动 '{analysis_type}' 数据分析，来源：{data_source}",
            },
            metadata={"analysis_type": analysis_type},
        )