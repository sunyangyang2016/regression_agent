"""
回归测试：工具名称规范化（OpenAI 兼容 API 函数名）

背景问题：
OpenAI 兼容 API 要求 function.name 匹配 `^[a-zA-Z0-9_-]+$`。
MCP / 技能 / 内建工具的名称可能包含点号、空格、斜杠、中文等非法字符，
直接透传会触发 400：
    Invalid 'tools[N].function.name': string does not match pattern.

修复方案：
- ai/tool_names.py 提供批量规范化 + 「API 名 → 原始名」映射
- ai/client.py._get_tools_for_api 在发送前规范化并缓存映射
- ai/stream_handler.py._execute_tool_routed 在路由前把模型回调名还原为原始名
"""
import asyncio
import re

import ai.tool_names as tn
from ai.client import AIClient
from ai.stream_handler import StreamHandler

# OpenAI 兼容 API 的函数名约束
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


# ==========================================
# ai.tool_names 单元测试
# ==========================================

def test_sanitize_tool_name_replaces_invalid_chars():
    assert tn.sanitize_tool_name("get.weather") == "get_weather"
    assert tn.sanitize_tool_name("server/tool name") == "server_tool_name"
    assert tn.sanitize_tool_name("we  ir d..name") == "we_ir_d_name"
    assert tn.sanitize_tool_name("a#b$c") == "a_b_c"
    assert tn.sanitize_tool_name("") == "tool"
    assert tn.sanitize_tool_name(None) == "tool"
    assert tn.sanitize_tool_name("...") == "tool"
    assert tn.sanitize_tool_name("查询天气") == "tool"


def test_sanitize_tool_name_keeps_valid():
    assert tn.sanitize_tool_name("calculate") == "calculate"
    assert tn.sanitize_tool_name("mcp_server-tool_1") == "mcp_server-tool_1"


def test_sanitize_output_always_matches_openai_pattern():
    for name in ["a.b", "你好世界", "foo bar", "foo/bar:baz", "a#b$c", "x y", "...", "123", "s v-2_1"]:
        out = tn.sanitize_tool_name(name)
        assert _NAME_PATTERN.match(out), f"{name!r} -> {out!r}"


def test_is_valid_tool_name():
    assert tn.is_valid_tool_name("abc_123-xyz")
    assert not tn.is_valid_tool_name("abc.123")
    assert not tn.is_valid_tool_name("")
    assert not tn.is_valid_tool_name("你好")
    assert not tn.is_valid_tool_name("a b")


def test_sanitize_tools_for_api_passes_valid_through_unchanged():
    tools = [
        {"type": "function", "function": {"name": "calculate", "description": "d", "parameters": {}}},
        {"type": "function", "function": {"name": "web_search", "description": "d", "parameters": {}}},
    ]
    result, name_map = tn.sanitize_tools_for_api(tools)
    # 合法名称直接透传（同一对象），且不产生映射
    assert result == tools
    assert name_map == {}
    assert result[0]["function"]["name"] == "calculate"


def test_sanitize_tools_for_api_renames_invalid_and_maps():
    tools = [
        {"type": "function", "function": {"name": "server.get_weather", "description": "d", "parameters": {}}},
        {"type": "function", "function": {"name": "查询天气", "description": "d", "parameters": {}}},
    ]
    result, name_map = tn.sanitize_tools_for_api(tools)
    names = [t["function"]["name"] for t in result]
    for n in names:
        assert _NAME_PATTERN.match(n), n
    assert name_map["server_get_weather"] == "server.get_weather"
    assert name_map["tool"] == "查询天气"
    # 调用方传入的原始对象不应被修改
    assert tools[0]["function"]["name"] == "server.get_weather"
    assert tools[1]["function"]["name"] == "查询天气"


def test_sanitize_tools_for_api_resolves_collisions():
    tools = [
        {"type": "function", "function": {"name": "foo.bar", "description": "d", "parameters": {}}},
        {"type": "function", "function": {"name": "foo_bar", "description": "d", "parameters": {}}},
        {"type": "function", "function": {"name": "foo/bar", "description": "d", "parameters": {}}},
    ]
    result, name_map = tn.sanitize_tools_for_api(tools)
    names = [t["function"]["name"] for t in result]
    # API 侧名称必须唯一
    assert len(set(names)) == 3, names
    assert name_map["foo_bar"] == "foo.bar"
    assert name_map["foo_bar_2"] == "foo_bar"
    assert name_map["foo_bar_3"] == "foo/bar"


# ==========================================
# AIClient 集成测试
# ==========================================

def test_get_tools_for_api_sanitizes_all_sources_and_maps(monkeypatch):
    client = object.__new__(AIClient)
    client._tool_name_map = {}

    def fake_builtin():
        return [
            {"type": "function", "function": {"name": "calculate", "description": "d", "parameters": {}}},
            {"type": "function", "function": {"name": "run.command", "description": "d", "parameters": {}}},
        ]

    def fake_mcp():
        return [
            {"type": "function", "function": {"name": "mcp/tool 1", "description": "d", "parameters": {}}},
        ]

    def fake_skill():
        return [
            {"type": "function", "function": {"name": "skill_查询", "description": "d", "parameters": {}}},
        ]

    monkeypatch.setattr(client, "_get_builtin_tools", fake_builtin)
    monkeypatch.setattr(client, "_get_mcp_tools", fake_mcp)
    monkeypatch.setattr(client, "_get_skill_tools", fake_skill)

    tools = client._get_tools_for_api()
    assert len(tools) == 4
    for t in tools:
        assert _NAME_PATTERN.match(t["function"]["name"]), t["function"]["name"]

    # 模型回调名 → 原始工具名 的还原
    assert client._resolve_tool_api_name("calculate") == "calculate"
    assert client._resolve_tool_api_name("run_command") == "run.command"
    assert client._resolve_tool_api_name("mcp_tool_1") == "mcp/tool 1"
    assert client._resolve_tool_api_name("skill") == "skill_查询"
    # 未注册名原样返回
    assert client._resolve_tool_api_name("unknown_tool") == "unknown_tool"


class _FakeDispatcher:
    """模拟 ToolDispatcher：只认识指定的工具名"""

    def __init__(self, names):
        self._names = set(names)

    def has_tool(self, name):
        return name in self._names

    async def execute(self, name, arguments):
        return f"executed:{name}"


def test_execute_tool_routed_resolves_sanitized_name():
    """模型回调规范化名 → 还原为原始名后路由执行"""
    sh = object.__new__(StreamHandler)
    sh.tool_dispatcher = _FakeDispatcher({"skill_查询"})
    sh.mcp_dispatcher = None
    name_map = {"skill": "skill_查询"}
    sh.name_resolver = lambda n: tn.resolve_original_name(name_map, n)

    result = asyncio.run(sh._execute_tool_routed("skill", {"query": "x"}))
    assert result == "executed:skill_查询"


def test_execute_tool_routed_uses_internal_name_map():
    """stream_chat 内建映射也可还原名称（不依赖外部 name_resolver）"""
    sh = object.__new__(StreamHandler)
    sh.tool_dispatcher = _FakeDispatcher({"pixlint.classify image/风景照"})
    sh.mcp_dispatcher = None
    sh.name_resolver = None
    sh._tool_name_map = {"pixlint_classify_image": "pixlint.classify image/风景照"}

    result = asyncio.run(sh._execute_tool_routed("pixlint_classify_image", {}))
    assert result == "executed:pixlint.classify image/风景照"



def test_execute_tool_routed_keeps_valid_name():
    """合法名无需还原，原样路由"""
    sh = object.__new__(StreamHandler)
    sh.tool_dispatcher = _FakeDispatcher({"calculate"})
    sh.mcp_dispatcher = None
    sh.name_resolver = lambda n: n

    result = asyncio.run(sh._execute_tool_routed("calculate", {"a": 1}))
    assert result == "executed:calculate"


def test_resolve_original_name():
    name_map = {"get_weather": "get.weather"}
    assert tn.resolve_original_name(name_map, "get_weather") == "get.weather"
    # 不在映射中（合法名或模型幻觉）原样返回
    assert tn.resolve_original_name(name_map, "calculate") == "calculate"
    assert tn.resolve_original_name({}, "x") == "x"
