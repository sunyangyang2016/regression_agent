"""
回归测试：MCP 后台加载期间，AI 发送消息不应被 MCP 服务器启动过程阻塞。

背景问题：
- 启动时 MCPHost 在后台线程串行加载所有已配置的 MCP 服务器，
  整个加载期间 MCPHost._loading = True（可能长达十几秒）。
- 修复前 ai/client.py 的 _get_mcp_tools / _inject_mcp_server_context
  会同步忙等 _loading 变 False（最多 15 秒），导致用户消息被拖住，
  “等到所有 MCP server 加载完成后 AI 才应答”。
- 修复后改为直接使用当前已加载的工具/状态快照，立即返回；
  同时 MCPHost.get_tools / get_all_servers 遍历 _clients 时先做快照，
  避免与后台加载线程并发修改字典抛异常。
"""
import threading
import time

import tools.mcp.host as host_module
from ai.client import AIClient


class _FakeTool:
    def __init__(self, name):
        self.name = name


class _FakeClient:
    """模拟一个已上线的 MCP 客户端（纯内存，不启动子进程）"""

    def __init__(self, names=None):
        self._tools = [_FakeTool(n) for n in (names or [])]

    def list_tools(self):
        return self._tools

    def get_openai_tools(self):
        return [{
            "type": "function",
            "function": {
                "name": t.name,
                "description": "fake desc",
                "parameters": {},
            },
        } for t in self._tools]

    def is_running(self):
        return True


class _FakeHost:
    """模拟仍在后台加载中的 MCPHost（_loading=True）"""

    def __init__(self, loading=True):
        self._loading = loading
        self._clients = {"server_a": _FakeClient(["tool_a"])}
        self._tool_handlers = {}

    def get_tools(self):
        return list(self._clients.values())[0].get_openai_tools()

    def get_all_servers(self):
        client = self._clients.get("server_a")
        return [{
            "id": "server_a",
            "name": "server_a",
            "url": "",
            "description": "",
            "transport": "stdio",
            "enabled": True,
            "online": bool(client) and client.is_running(),
        }]


def _patch_host(monkeypatch, fake):
    """让 ai.client 里 `from tools.mcp.host import MCPHost` 返回 fake"""
    monkeypatch.setattr(host_module, "MCPHost", lambda *a, **k: fake)


def test_get_mcp_tools_returns_immediately_while_loading(monkeypatch):
    """核心回归：_loading=True 时 _get_mcp_tools 必须立即返回，不能忙等 15 秒。"""
    _patch_host(monkeypatch, _FakeHost(loading=True))
    client = object.__new__(AIClient)

    start = time.time()
    tools = client._get_mcp_tools()
    elapsed = time.time() - start

    assert elapsed < 1.0, f"_get_mcp_tools 被阻塞了 {elapsed:.1f}s（不应等待 MCP 加载）"
    assert [t["function"]["name"] for t in tools] == ["tool_a"]


def test_inject_mcp_context_returns_immediately_while_loading(monkeypatch):
    """核心回归：_loading=True 时 _inject_mcp_server_context 必须立即返回。"""
    _patch_host(monkeypatch, _FakeHost(loading=True))
    client = object.__new__(AIClient)
    client._system_prompt = "SYSTEM"

    start = time.time()
    client._inject_mcp_server_context()
    elapsed = time.time() - start

    assert elapsed < 1.0, f"_inject_mcp_server_context 被阻塞了 {elapsed:.1f}s"
    assert "## MCP 服务器状态" in client._system_prompt


def test_inject_mcp_context_skips_when_no_servers(monkeypatch):
    """没有任何已配置服务器时，不注入上下文、不报错。"""
    fake = _FakeHost(loading=True)
    fake._clients = {}
    fake.get_all_servers = lambda: []
    _patch_host(monkeypatch, fake)
    client = object.__new__(AIClient)
    client._system_prompt = "SYSTEM"

    client._inject_mcp_server_context()

    assert client._system_prompt == "SYSTEM"


def test_host_get_tools_thread_safe_during_concurrent_insert():
    """get_tools 在后台线程并发插入 _clients 时必须安全（快照遍历）。"""
    host = object.__new__(host_module.MCPHost)
    host._clients = {"a": _FakeClient(["tool_a"])}

    def insert_loop():
        # 无工具客户端避免 get_tools 内每个 client 都打印，控制测试耗时
        for i in range(2000):
            host._clients[f"srv_{i}"] = _FakeClient()
        host._clients["zz_last"] = _FakeClient(["tool_b"])

    t = threading.Thread(target=insert_loop, daemon=True)
    t.start()
    try:
        for _ in range(200):
            tools = host.get_tools()
            assert isinstance(tools, list)
    finally:
        t.join(timeout=10)


def test_host_get_all_servers_thread_safe_during_concurrent_insert():
    """get_all_servers 在后台线程并发插入 _clients 时必须安全（快照遍历）。"""
    host = object.__new__(host_module.MCPHost)
    host._clients = {"a": _FakeClient(["tool_a"])}
    host._read_config = lambda: {
        "mcpServers": {
            "a": {"transport": "stdio", "enabled": True, "name": "A",
                  "url": "", "description": ""}
        }
    }

    def insert_loop():
        for i in range(2000):
            host._clients[f"srv_{i}"] = _FakeClient()
        host._clients["zz_last"] = _FakeClient(["tool_b"])

    t = threading.Thread(target=insert_loop, daemon=True)
    t.start()
    try:
        for _ in range(200):
            servers = host.get_all_servers()
            assert isinstance(servers, list)
            assert servers[0]["id"] == "a"
    finally:
        t.join(timeout=10)


def test_host_wait_ready_non_blocking_by_default():
    """wait_ready(timeout=0) 默认不等待，加载中直接返回 False。"""
    host = object.__new__(host_module.MCPHost)
    host._loading = True
    assert host.wait_ready() is False
    host._loading = False
    assert host.wait_ready() is True


def test_load_servers_from_config_runs_in_parallel(monkeypatch):
    """核心回归：_load_servers_from_config 并行启动服务器，总耗时明显小于串行。"""
    host = object.__new__(host_module.MCPHost)
    host._read_config = lambda: {
        "mcpServers": {
            "a": {"enabled": True},
            "b": {"enabled": True},
            "c": {"enabled": True},
            "d": {"enabled": True},
        }
    }

    started = []
    lock = threading.Lock()

    def fake_register(sid, cfg):
        with lock:
            started.append(sid)
        time.sleep(0.3)
        return True

    host.register_client = fake_register

    fired = {"n": 0}

    def fake_fire():
        fired["n"] += 1

    monkeypatch.setattr(host_module.MCPHost, "_fire_status_change", staticmethod(fake_fire))

    start = time.time()
    host._load_servers_from_config()
    elapsed = time.time() - start

    # 4 个服务器 × 0.3s：串行需 ≥1.2s，并行应明显小于 1.0s
    assert elapsed < 1.0, f"并行加载耗时 {elapsed:.2f}s，疑似退化为串行"
    assert sorted(started) == ["a", "b", "c", "d"]
    assert fired["n"] == 5  # 4 个成功各触发一次状态刷新 + 最终一次


def test_load_servers_skips_disabled_and_fires_once_for_config(monkeypatch):
    """禁用的服务器不启动；配置里存在服务器但全部禁用时仍触发一次状态刷新。"""
    host = object.__new__(host_module.MCPHost)
    host._read_config = lambda: {
        "mcpServers": {
            "a": {"enabled": False},
            "b": {"enabled": False},
        }
    }

    called = []
    host.register_client = lambda sid, cfg: called.append(sid) or True

    fired = {"n": 0}

    def fake_fire():
        fired["n"] += 1

    monkeypatch.setattr(host_module.MCPHost, "_fire_status_change", staticmethod(fake_fire))

    host._load_servers_from_config()

    assert called == []
    assert fired["n"] == 1

