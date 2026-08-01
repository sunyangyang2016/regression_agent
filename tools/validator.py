"""
工具验证器 - 验证工具调用参数
"""
from typing import Any, Dict, List, Optional, Tuple


class ToolValidator:
    """工具调用参数验证器"""

    @staticmethod
    def validate_args(args: Dict[str, Any], schema: Dict) -> Tuple[bool, List[str]]:
        """根据 JSON Schema 验证参数"""
        errors = []
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # 检查必填字段
        for field in required:
            if field not in args:
                errors.append(f"缺少必填参数: {field}")

        # 检查参数类型和格式
        for field, value in args.items():
            if field not in properties:
                continue
            field_schema = properties[field]
            expected_type = field_schema.get("type")

            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"参数 '{field}' 应为字符串")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"参数 '{field}' 应为整数")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"参数 '{field}' 应为数字")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"参数 '{field}' 应为布尔值")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"参数 '{field}' 应为数组")
            elif expected_type == "object" and not isinstance(value, dict):
                errors.append(f"参数 '{field}' 应为对象")

            # 检查枚举值
            if "enum" in field_schema and value not in field_schema["enum"]:
                errors.append(f"参数 '{field}' 值不在允许范围内: {field_schema['enum']}")

        return len(errors) == 0, errors

    @staticmethod
    def sanitize_args(args: Dict[str, Any], schema: Dict) -> Dict[str, Any]:
        """清理参数，移除未定义的字段"""
        properties = schema.get("properties", {})
        return {k: v for k, v in args.items() if k in properties}

    @staticmethod
    def coerce_types(args: Dict[str, Any], schema: Dict) -> Dict[str, Any]:
        """尝试类型转换"""
        result = {}
        properties = schema.get("properties", {})
        for field, value in args.items():
            if field not in properties:
                result[field] = value
                continue
            expected = properties[field].get("type")
            if expected == "integer" and isinstance(value, str):
                try:
                    result[field] = int(value)
                except (ValueError, TypeError):
                    result[field] = value
            elif expected == "number" and isinstance(value, str):
                try:
                    result[field] = float(value)
                except (ValueError, TypeError):
                    result[field] = value
            else:
                result[field] = value
        return result