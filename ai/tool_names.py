"""
工具名称规范化（OpenAI 兼容 API 函数名）

OpenAI 兼容 API 对 function 名称有严格限制：
    ^[a-zA-Z0-9_-]+$

实际场景中工具名可能来自：
- MCP 服务器（名称可能包含点号、空格、斜杠，如 "server.tool_name"、"get weather"）
- 技能（skill_{中文名}）
- 内建工具

名称含非法字符时直接透传会触发 400 invalid_request_error：
    Invalid 'tools[N].function.name': string does not match pattern.

本模块解决两个问题：
1. sanitize_tool_name() —— 将任意名称规范化为合法函数名
2. sanitize_tools_for_api() —— 批量规范化 + 建立「API 名称 → 原始名称」映射，
   供模型回调时还原真实工具名，确保执行路由不受影响
"""

import re
from typing import Dict, List, Tuple

# OpenAI 兼容 API 允许的函数名模式
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
# 非法字符（统一替换为下划线）
_INVALID_CHAR = re.compile(r"[^a-zA-Z0-9_-]")
# 连续下划线
_MULTI_UNDERSCORE = re.compile(r"_+")

# 规范化结果为空时的回退名
_FALLBACK_NAME = "tool"


def is_valid_tool_name(name: str) -> bool:
    """判断名称是否满足 OpenAI 函数名约束 `^[a-zA-Z0-9_-]+$`"""
    return bool(name) and bool(_NAME_PATTERN.match(name))


def sanitize_tool_name(name: str) -> str:
    """将任意工具名规范化为合法函数名。

    规则：
    1. 非 [a-zA-Z0-9_-] 字符替换为下划线
    2. 连续下划线压缩为单个下划线
    3. 去除首尾下划线
    4. 结果为空时回退为 "tool"

    >>> sanitize_tool_name("get.weather")
    'get_weather'
    >>> sanitize_tool_name("server/tool name")
    'server_tool_name'
    >>> sanitize_tool_name("")
    'tool'
    """
    if not name:
        return _FALLBACK_NAME
    cleaned = _INVALID_CHAR.sub("_", str(name))
    cleaned = _MULTI_UNDERSCORE.sub("_", cleaned).strip("_")
    return cleaned or _FALLBACK_NAME


def sanitize_tools_for_api(tools: List[dict]) -> Tuple[List[dict], Dict[str, str]]:
    """批量规范化 OpenAI tools 定义，并返回名称映射。

    Args:
        tools: OpenAI 格式工具列表
            [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}, ...]

    Returns:
        (sanitized_tools, name_map)
        name_map: {API 中使用的规范化名称: 原始工具名}
        仅包含发生变化的名称；原本合法的名称不产生映射条目。

    冲突处理：多个原始名规范化后相同（如 "foo.bar" 与 "foo_bar"）时，
    后续名称追加 "_2"、"_3" … 后缀保证 API 侧名称唯一。
    """
    result: List[dict] = []
    name_map: Dict[str, str] = {}
    used: set = set()

    for tool in tools or []:
        try:
            fn = tool.get("function") or {}
            original = fn.get("name")
            if not original:
                result.append(tool)
                continue
            original = str(original)

            # 名称合法且未被占用，直接透传（不修改原始对象）
            if is_valid_tool_name(original) and original not in used:
                used.add(original)
                result.append(tool)
                continue

            base = sanitize_tool_name(original)
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used.add(candidate)
            name_map[candidate] = original

            # 浅拷贝后替换 name，避免污染调用方持有的原始定义
            new_tool = dict(tool)
            new_fn = dict(fn)
            new_fn["name"] = candidate
            new_tool["function"] = new_fn
            result.append(new_tool)
        except Exception:
            # 单个工具处理失败不应阻断整体请求，原样保留
            result.append(tool)

    return result, name_map


def resolve_original_name(name_map: Dict[str, str], api_name: str) -> str:
    """将模型回调的工具名还原为原始名称。

    名称不在映射中（如本身合法或模型幻觉）时原样返回。
    """
    return name_map.get(api_name, api_name)
