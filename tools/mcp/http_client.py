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
        self._on_auth_required = on_auth_required
    
    def _make_headers(self, extra: dict = None) -> dict:
        import urllib.request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'MCP-Agent/1.0'
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
                    print(f"🔑 [MCPHTTP:{self.server_id}] 需要认证 (401)")
                    if self._on_auth_required:
                        self._on_auth_required(f"为 {self.server_id} 输入 API Key (从 {self.base_url} 获取)")
                        _time.sleep(0.5)
                        for key in ['API_KEY', 'API_TOKEN', 'TOKEN', 'AUTH_TOKEN', 'ACCESS_TOKEN']:
                            if key in self.env and self.env[key]:
                                self._api_key = self.env[key]
                                continue
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
                            return False
                    except Exception:
                        return False
                elif e.code == 404:
                    print(f"❌ [MCPHTTP:{self.server_id}] 端点不存在")
                    return False
                else:
                    print(f"❌ [MCPHTTP:{self.server_id}] HTTP {e.code}: {e.reason}")
                    return False
            except urllib.error.URLError as e:
                print(f"❌ [MCPHTTP:{self.server_id}] 连接失败: {e.reason}")
                return False
            
            if self._running:
                notif_payload = json.dumps({
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }).encode('utf-8')
                try:
                    msg_url = self._messages_url or self.base_url
                    headers = {'Content-Type': 'application/json', 'User-Agent': 'MCP-Agent/1.0'}
                    if self._session_id:
                        headers['Mcp-Session-Id'] = self._session_id
                    notif_req = urllib.request.Request(msg_url, data=notif_payload, headers=headers)
                    urllib.request.urlopen(notif_req, timeout=10)
                    print(f"📋 [MCPHTTP:{self.server_id}] ✅ initialized 已发送")
                except Exception as e:
                    print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ initialized 通知失败: {e}")
            
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
                        msg_url, data=tools_payload, headers=self._make_headers({'Accept': 'application/json'})
                    )
                    tools_resp = urllib.request.urlopen(tools_req, timeout=15)
                    tools_data = tools_resp.read().decode('utf-8', errors='replace')
                    
                    try:
                        tools_result = json.loads(tools_data)
                        if 'result' in tools_result:
                            tools_list = tools_result['result'].get('tools', [])
                        else:
                            tools_list = []
                        if tools_list:
                            for t in tools_list:
                                mt = MCPTool(
                                    name=t["name"],
                                    description=t.get("description", ""),
                                    parameters=t.get("inputSchema", {})
                                )
                                self._tools.append(mt)
                                print(f"    - {t['name']}: {t.get('description','')[:60]}")
                            print(f"📋 [MCPHTTP:{self.server_id}] ✅ 获取到 {len(tools_list)} 个工具")
                        else:
                            print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ 未获取到工具列表")
                    except json.JSONDecodeError:
                        print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ tools/list 响应非 JSON")
                except urllib.error.HTTPError as e:
                    print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ tools/list HTTP {e.code}")
                except Exception as e:
                    print(f"📋 [MCPHTTP:{self.server_id}] ⚠️ tools/list 失败: {e}")
            
            print(f"✅ HTTP MCP {self.server_id} 启动成功 ({len(self._tools)} 工具)")
            return True
        
        return False
    
    def _send(self, data: str) -> Optional[dict]:
        import urllib.request
        import urllib.error
        
        self._req_id += 1
        payload = data.encode('utf-8')
        
        try:
            msg_url = self._messages_url or self.base_url
            req = urllib.request.Request(msg_url, data=payload, headers=self._make_headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = resp.read().decode('utf-8', errors='replace')
                try:
                    return json.loads(resp_data)
                except json.JSONDecodeError:
                    print(f"📋 [MCPHTTP:{self.server_id}] 响应非 JSON: {resp_data[:200]}")
                    return None
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
