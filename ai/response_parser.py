"""
AI 响应解析器 - 解析 AI 返回的文本、工具调用等
"""
import json
import re
import html
from typing import Any, Dict, List, Optional, Tuple


class ResponseParser:
    """AI 响应解析器"""

    @staticmethod
    def parse_content(content: str) -> Dict[str, Any]:
        """解析 AI 返回内容，分离文本和工具调用"""
        result = {"text": content, "tool_calls": []}

        # 检测工具调用格式（如 <tool>...</tool> 或函数调用）
        tool_pattern = re.compile(r'<tool>(.*?)</tool>', re.DOTALL)
        for match in tool_pattern.finditer(content):
            try:
                tool_data = json.loads(match.group(1).strip())
                result["tool_calls"].append(tool_data)
            except json.JSONDecodeError:
                pass

        # 检测 Anthropic/Claude 格式的工具调用 <｜｜DSML｜｜tool_calls><invoke>...</invoke></｜｜DSML｜｜tool_calls>
        anthropic_calls = ResponseParser.parse_anthropic_tool_calls(content)
        if anthropic_calls:
            result["tool_calls"].extend(anthropic_calls)
            # 移除 <｜｜DSML｜｜tool_calls> 块，保留其余文本
            result["text"] = re.sub(
                r'<｜｜DSML｜｜tool_calls>.*?</｜｜DSML｜｜tool_calls>', "", content, flags=re.DOTALL
            ).strip()
            return result

        # 移除工具调用标记，保留纯文本
        result["text"] = tool_pattern.sub("", content).strip()
        return result

    @staticmethod
    def parse_anthropic_tool_calls(content: str) -> List[Dict[str, Any]]:
        """解析 Anthropic/Claude 格式的 <｜｜DSML｜｜tool_calls> 工具调用块

        支持的 XML 结构：
            <｜｜DSML｜｜tool_calls>
            <invoke name="tool_name">
            <parameter name="param1">value1</parameter>
            <parameter name="param2">value2</parameter>
            </invoke>
            </｜｜DSML｜｜tool_calls>

        返回 OpenAI tool_calls 兼容格式：
            [{
                "id": "anthropic-1",
                "type": "function",
                "function": {"name": "tool_name", "arguments": "{...}"}
            }]
        解析失败返回空列表。
        """
        if "<｜｜DSML｜｜tool_calls>" not in content:
            return []

        calls: List[Dict[str, Any]] = []
        # 匹配整个 <｜｜DSML｜｜tool_calls> 块
        block_match = re.search(
            r'<｜｜DSML｜｜tool_calls>(.*?)</｜｜DSML｜｜tool_calls>', content, re.DOTALL)
        if not block_match:
            return []
        block = block_match.group(1)

        # 匹配每个 <invoke> 块（内部含嵌套 <parameter>，需 lazy + DOTALL）
        invoke_pattern = re.compile(
            r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', re.DOTALL
        )
        for idx, inv in enumerate(invoke_pattern.finditer(block), start=1):
            tool_name = inv.group(1).strip()
            body = inv.group(2)

            # 提取所有 <parameter name="...">...</parameter>
            params = {}
            param_pattern = re.compile(
                r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.DOTALL
            )
            for pm in param_pattern.finditer(body):
                pname = pm.group(1).strip()
                pvalue = pm.group(2).strip()
                # 解码 HTML 实体（如 & <），并去掉多余空行
                pvalue = html.unescape(pvalue)
                # 尝试将数值字符串转为 JSON 类型（数字/布尔/null）
                if pvalue in ("true", "false"):
                    pvalue = pvalue == "true"
                elif pvalue == "null":
                    pvalue = None
                else:
                    try:
                        pvalue = int(pvalue)
                    except (ValueError, TypeError):
                        try:
                            pvalue = float(pvalue)
                        except (ValueError, TypeError):
                            pass
                params[pname] = pvalue

            if tool_name and params:
                calls.append({
                    "id": f"anthropic-{idx}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(params, ensure_ascii=False)
                    }
                })

        return calls

    @staticmethod
    def parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
        """解析工具调用文本"""
        # 支持 JSON 格式工具调用
        try:
            data = json.loads(text)
            if "name" in data and "arguments" in data:
                return data
        except json.JSONDecodeError:
            pass

        # 支持 function_call 格式
        func_match = re.search(r'(\w+)\((.*)\)', text, re.DOTALL)
        if func_match:
            return {
                "name": func_match.group(1),
                "arguments": func_match.group(2).strip(),
            }
        return None

    @staticmethod
    def parse_stream_chunk(chunk: str) -> Dict[str, Any]:
        """解析流式响应块"""
        result = {"content": "", "tool_call": None, "is_final": False}

        if chunk.startswith("data: "):
            chunk = chunk[6:].strip()

        if chunk == "[DONE]":
            result["is_final"] = True
            return result

        try:
            data = json.loads(chunk)
            delta = data.get("choices", [{}])[0].get("delta", {})

            if "content" in delta:
                result["content"] = delta["content"]

            if "tool_calls" in delta:
                result["tool_call"] = delta["tool_calls"]

            finish_reason = data.get("choices", [{}])[0].get("finish_reason")
            if finish_reason and finish_reason != "null":
                result["is_final"] = True

        except (json.JSONDecodeError, KeyError, IndexError):
            result["content"] = chunk

        return result

    @staticmethod
    def extract_code_blocks(text: str) -> List[Dict[str, str]]:
        """提取文本中的代码块"""
        blocks = []
        pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
        for match in pattern.finditer(text):
            blocks.append({
                "language": match.group(1) or "text",
                "code": match.group(2).strip(),
            })
        return blocks

    @staticmethod
    def extract_json(text: str) -> Optional[Any]:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试从代码块中提取
        blocks = ResponseParser.extract_code_blocks(text)
        for block in blocks:
            if block["language"] == "json":
                try:
                    return json.loads(block["code"])
                except json.JSONDecodeError:
                    continue
        # 尝试从文本中提取 {...} 或 [...]
        json_pattern = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if json_pattern:
            try:
                return json.loads(json_pattern.group())
            except json.JSONDecodeError:
                pass
        return None