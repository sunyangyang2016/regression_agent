"""
数据导出技能 - 将数据导出为 CSV、Excel 等格式
"""
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext


class DataExportSkill(BaseSkill):
    """数据导出技能"""

    name = "data_export"
    description = "将数据导出为 CSV、Excel、JSON 等格式，支持数据清洗和转换"
    category = "data"
    tags = ["export", "csv", "excel", "data", "conversion"]
    input_schema = {
        "type": "object",
        "properties": {
            "data": {"type": "string", "description": "要导出的数据内容（JSON 或表格文本）"},
            "format": {"type": "string", "description": "导出格式: csv, excel, json, markdown", "enum": ["csv", "excel", "json", "markdown"]},
            "filename": {"type": "string", "description": "导出文件名（不含扩展名，可选）"},
        },
        "required": ["data", "format"],
    }

    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        data = kwargs.get("data", context.get("data", ""))
        export_format = kwargs.get("format", context.get("format", "csv"))
        filename = kwargs.get("filename", context.get("filename", "export"))

        return SkillResult(
            success=True,
            output={
                "format": export_format,
                "filename": filename,
                "data_length": len(data),
                "message": f"数据导出请求：{len(data)} 字符 → {export_format} 格式（文件名：{filename}）",
            },
            metadata={"format": export_format, "filename": filename},
        )