"""
MCPHTTPClient - MCP HTTP 客户端（通过 HTTP/SSE 与远程 MCP 服务通信）
"""
import json
import time
from typing import Optional
from tools.mcp.protocols import (
    build_initialize,
    build_initialized_notification,
    build_tools_list,
    build_tools_call,
)
from tools.mcp.protocols.tool import MCPTool


class MCPHTTPClient:
    """MCP HTTP 客户端 — 通过 HTTP/SSE 与远程 MCP 服务通信"""
    
    def __init__(self, server_id: str, url: str, env: dict = None, on_auth_required: callable = None):
        self.server_id = server_id
        self.base_url = url.rstrip('/')
        self.env = env or {}
        self._tools: list = []
        self._session_id: Optional[str] = None
        self._messages_url: Optional[str] = None
        self._running = False
        self._req_id = 0
        self._api_key = None
        self.last_error = ""
        self._on_auth_required = on_auth_required
    
    def _make_headers(self, extra: dict = None) -> dict:
        import urllib.request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'MCP-Agent/1.0',
            'MCP-Protocol-Version': '2024-11-05'   # Streamable HTTP 必需，缺失会被服务端拒(400)
        }
        if self._api_key:
            headers['Authorization'] = f'Bearer {self._api_key}'
            headers['X-Api-Key'] = self._api_key
        if self._session_id:
            headers['Mcp-Session-Id'] = self._session_id
        if extra:
            headers.update(extra)
        return headers
    
    def start(self) -> bool:
        """启动 HTTP 连接：初始化 + SSE + tools/list"""
        import urllib.request
        import urllib.error
        
        print(f"🌐 [MCPHTTP:{self.server_id}] 连接远程服务: {self.base_url}")
        
        for key in ['API_KEY', 'API_TOKEN', 'TOKEN', 'AUTH_TOKEN', 'ACCESS_TOKEN']:
            if key in self.env and self.env[key]:
                self._api_key = self.env[key]
                print(f"📋 [MCPHTTP:{self.server_id}] 从配置加载认证 Key")
                break
        
        import time as _time
        
        for attempt in range(2):
            if attempt == 1 and not self._api_key:
                print(f"❌ [MCPHTTP:{self.server_id}] 无 API Key，无法重试")
                break
                
            init_payload = build_initialize().encode('utf-8')
            
            req = urllib.request.Request(
                self.base_url,
                data=init_payload,
                headers=self._make_headers({'Accept': 'text/event-stream, application/json'})
            )
            
            try:
                resp = urllib.request.urlopen(req, timeout=15)
                resp_data = resp.read().decode('utf-8', errors='replace')
                
                session_id = resp.headers.get('Mcp-Session-Id') or resp.headers.get('mcp-session-id')
                
                init_result = None
                try:
                    init_result = json.loads(resp_data)
                except json.JSONDecodeError:
                    pass
                
                if not session_id:
                    for line in resp_data.split('\n'):
                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])
                                if isinstance(data, dict) and 'sessionId' in data:
                                    session_id = data['sessionId']
                                elif isinstance(data, dict) and 'result' in data:
                                    init_result = data
                            except json.JSONDecodeError:
                                pass
                
                if init_result and 'result' in init_result:
                    result = init_result['result']
                    server_info = result.get('serverInfo', {})
                    print(f"📋 [MCPHTTP:{self.server_id}]   服务器信息: {server_info.get('name','?')} v{server_info.get('version','?')}")
                
                self._messages_url = resp.headers.get('Mcp-Messages-Url') or resp.headers.get('mcp-messages-url')
                
                if session_id:
                    self._session_id = session_id
                    print(f"📋 [MCPHTTP:{self.server_id}] ✅ 连接成功, session_id={session_id[:20]}...")
                else:
                    print(f"📋 [MCPHTTP:{self.server_id}] ✅ 连接成功 (无 session_id)")
                
                self._running = True
                
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    # 401 = 需要认证
                    if self._api_key:
                        # 配置里已有 Key 就不再弹窗，提示 Key 可能无效
                        self.last_error = "HTTP 401: 已携带 API Key 但仍被拒绝，请检查 Key 是否有效"
                        print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                        try:
                            err_body = e.read().decode('utf-8', errors='replace')[:200]
                            if err_body:
                                print(f"❌ [MCPHTTP:{self.server_id}]   响应体: {err_body}")
                        except Exception:
                            pass
                        return False
                    # 无 Key 才弹窗
                    self.last_error = "HTTP 401: 需要 API Key 认证，已弹出输入框"
                    print(f"🔑 [MCPHTTP:{self.server_id}] 需要认证 (401)，弹出 Key 输入框")
                    if self._on_auth_required:
                        self._on_auth_required(f"为 {self.server_id} 输入 API Key (从 {self.base_url} 获取)")
                        _time.sleep(0.5)
                        for key in ['API_KEY', 'API_TOKEN', 'TOKEN', 'AUTH_TOKEN', 'ACCESS_TOKEN']:
                            if key in self.env and self.env[key]:
                                self._api_key = self.env[key]
                                continue
                    return False
                elif e.code == 403:
                    # 403 = 已认证但被拒绝（权限不足/白名单/端点错误）
                    if self._api_key:
                        self.last_error = "HTTP 403: 已携带 API Key 但仍被拒绝"
                        print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                        print(f"❌ [MCPHTTP:{self.server_id}]   可能原因: Key 无效 / URL 路径不是正确 MCP 端点 / 服务端 IP 白名单限制")
                    else:
                        self.last_error = "HTTP 403: 连接被拒绝，可能需要 API Key"
                        print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                        print(f"❌ [MCPHTTP:{self.server_id}]   可能原因: 需要 API Key / URL 路径不是正确 MCP 端点 / 服务端 IP 白名单限制")
                        if self._on_auth_required and not self._api_key:
                            print(f"🔑 [MCPHTTP:{self.server_id}] 尝试弹出 Key 输入框")
                            self._on_auth_required(f"为 {self.server_id} 输入 API Key (从 {self.base_url} 获取)")
                            _time.sleep(0.5)
                    try:
                        err_body = e.read().decode('utf-8', errors='replace')[:200]
                        if err_body:
                            print(f"❌ [MCPHTTP:{self.server_id}]   响应体: {err_body}")
                            self.last_error += f" | 响应体: {err_body[:150]}"
                    except Exception:
                        pass
                    return False
                elif e.code == 405:
                    try:
                        get_req = urllib.request.Request(
                            self.base_url,
                            headers={'Accept': 'text/event-stream', 'User-Agent': 'MCP-Agent/1.0'}
                        )
                        get_resp = urllib.request.urlopen(get_req, timeout=15)
                        session_id = get_resp.headers.get('Mcp-Session-Id') or get_resp.headers.get('mcp-session-id')
                        self._messages_url = get_resp.headers.get('Mcp-Messages-Url') or get_resp.headers.get('mcp-messages-url')
                        if session_id:
                            self._session_id = session_id
                            self._running = True
                        else:
                            self.last_error = "HTTP 405: 未获取到 session_id"
                            return False
                    except Exception:
                        self.last_error = "HTTP 405: 回退 GET 请求失败"
                        return False
                elif e.code == 404:
                    self.last_error = "HTTP 404: 端点不存在，请检查 URL 路径是否为正确的 MCP 端点"
                    print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                    return False
                else:
                    self.last_error = f"HTTP {e.code}: {e.reason}"
                    print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                    try:
                        err_body = e.read().decode('utf-8', errors='replace')[:200]
                        if err_body:
                            print(f"❌ [MCPHTTP:{self.server_id}]   响应体: {err_body}")
                            self.last_error += f" | 响应体: {err_body[:150]}"
                    except Exception:
                        pass
                    return False
            except urllib.error.URLError as e:
                self.last_error = f"连接失败: {e.reason}"
                print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                return False
            
            if self._running:
                notif_payload = json.dumps({
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }).encode('utf-8')
                msg_url = self._messages_url or self.base_url
                if not self._messages_url:
                    print(f"⚠️ [MCPHTTP:{self.server_id}] 服务端未返回 Mcp-Messages-Url 头，通知将发往 base_url")
                # 尝试两种 Accept 顺序（不同服务端要求不同）
                notif_sent = False
                for accept_val in ('text/event-stream, application/json', 'application/json, text/event-stream'):
                    try:
                        headers = self._make_headers({'Accept': accept_val})
                        notif_req = urllib.request.Request(msg_url, data=notif_payload, headers=headers)
                        urllib.request.urlopen(notif_req, timeout=10)
                        print(f"📋 [MCPHTTP:{self.server_id}] ✅ initialized 已发送 (Accept: {accept_val})")
                        notif_sent = True
                        break
                    except urllib.error.HTTPError as e:
                        err_body = ""
                        try:
                            err_body = e.read().decode('utf-8', errors='replace')[:200]
                        except Exception:
                            pass
                        print(f"⚠️ [MCPHTTP:{self.server_id}] initialized HTTP {e.code} (Accept: {accept_val})"
                              + (f" | 响应体: {err_body}" if err_body else ""))
                    except Exception as e:
                        print(f"⚠️ [MCPHTTP:{self.server_id}] initialized 通知失败: {e}")
                if not notif_sent:
                    print(f"⚠️ [MCPHTTP:{self.server_id}] initialized 通知两次尝试均失败，继续尝试 tools/list")
            
            if self._running:
                self._req_id += 1
                tools_payload = json.dumps({
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": self._req_id
                }).encode('utf-8')
                try:
                    msg_url = self._messages_url or self.base_url
                    tools_req = urllib.request.Request(
                        msg_url, data=tools_payload, headers=self._make_headers({'Accept': 'text/event-stream, application/json'})
                    )
                    tools_resp = urllib.request.urlopen(tools_req, timeout=15)
                    tools_data = tools_resp.read().decode('utf-8', errors='replace')
                    tools_result = self._parse_mcp_response(tools_data)

                    if tools_result is None:
                        self.last_error = "tools/list 响应解析失败（非 JSON 也非 SSE）"
                        print(f"❌ [MCPHTTP:{self.server_id}] {self.last_error}")
                        print(f"❌ [MCPHTTP:{self.server_id}]   原始响应: {tools_data[:200]}")
                    else:
                        # 兼容多种响应结构
                        if 'result' in tools_result:
                            result_obj = tools_result['result']
                            if isinstance(result_obj, dict):
                                tools_list = result_obj.get('tools', [])
                            else:
                                tools_list = []
                        else:
                            tools_list = tools_result.get('tools', [])

                        if tools_list:
                            for t in tools_list:
                                mt = MCPTool(
                                    name=t.get("name", ""),
                                    description=t.get("description", ""),
                                    parameters=t.get("inputSchema", {})
                                )
                                if mt.name:
                                    self._tools.append(mt)
                                    print(f"    - {mt.name}: {mt.description[:60]}")
                            print(f"📋 [MCPHTTP:{self.server_id}] ✅ 获取到 {len(self._tools)} 个工具")
                        else:
                            print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ 服务端未返回工具列表")
                except urllib.error.HTTPError as e:
                    self.last_error = f"tools/list HTTP {e.code}"
                    print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ {self.last_error}")
                except Exception as e:
                    self.last_error = f"tools/list 失败: {str(e)[:80]}"
                    print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ {self.last_error}")
            
            print(f"✅ HTTP MCP {self.server_id} 启动成功 ({len(self._tools)} 工具)")
            return True
        
        return False
    
    def _parse_mcp_response(self, data: str) -> Optional[dict]:
        """解析 MCP HTTP 响应，兼容纯 JSON 和 SSE 格式

        MCP Streamable HTTP 协议的响应可能是：
        1. 纯 JSON: {"jsonrpc":"2.0","id":2,"result":{...}}
        2. SSE 格式:
           event: message
           data: {"jsonrpc":"2.0","id":2,"result":{...}}
        3. 简化 SSE:
           data: {"result":{...}}

        返回解析后的 JSON dict，失败返回 None。
        """
        if not data or not data.strip():
            return None
        # 1. 先尝试整体 JSON 解析
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            pass
        # 2. SSE 格式：逐行提取 data: 前缀的 JSON 负载
        try:
            for line in data.split('\n'):
                line = line.strip()
                if line.startswith('data:'):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            obj = json.loads(payload)
                            if isinstance(obj, dict):
                                return obj
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        # 3. 兼容多行 data（SSE 大数据块跨行）
        try:
            lines = []
            for line in data.split('\n'):
                line = line.strip()
                if line.startswith('data:'):
                    lines.append(line[5:].strip())
            if lines:
                combined = ''.join(lines)
                obj = json.loads(combined)
                if isinstance(obj, dict):
                    return obj
        except Exception:
            pass
        return None

    def _send(self, data: str) -> Optional[dict]:
        import urllib.request
        import urllib.error
        
        self._req_id += 1
        payload = data.encode('utf-8')
        
        try:
            msg_url = self._messages_url or self.base_url
            # 必须声明接受 SSE（与 tools/list 一致），否则服务端返回 406
            req = urllib.request.Request(
                msg_url, data=payload,
                headers=self._make_headers({'Accept': 'text/event-stream, application/json'})
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = resp.read().decode('utf-8', errors='replace')
                parsed = self._parse_mcp_response(resp_data)
                if parsed is None:
                    print(f"📋 [MCPHTTP:{self.server_id}] 响应解析失败: {resp_data[:200]}")
                return parsed
        except urllib.error.HTTPError as e:
            print(f"❌ [MCPHTTP:{self.server_id}] HTTP {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            print(f"❌ [MCPHTTP:{self.server_id}] 请求失败: {e.reason}")
            return None
    
    def list_tools(self) -> list:
        return self._tools
    
    def get_openai_tools(self) -> list:
        result = []
        for t in self._tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters
                }
            })
        return result
    
    def call_tool_sync(self, name: str, arguments: dict) -> str:
        return self.call_tool(name, arguments)

    def call_tool(self, name: str, arguments: dict) -> str:
        request = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": self._req_id + 1
        })
        print(f"📤 [MCP→HTTP:{self.server_id}] 调用工具 '{name}'")
        response = self._send(request)
        if response:
            if "error" in response:
                err = response["error"]
                return f"❌ 工具 {name} 调用失败: {err.get('message', '未知错误')}"
            result = response.get("result", {})
            content = result.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts)
        return f"❌ 工具 {name} 调用失败: 无响应"
    
    def is_running(self) -> bool:
        return self._running
    
    def cleanup_sync(self):
        self.cleanup()

    def cleanup(self):
        self._running = False
        print(f"⏹ HTTP MCP {self.server_id} 已断开")
