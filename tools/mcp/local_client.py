"""
MCPLocalClient - 标准 MCP 协议通信（子进程 + JSON-RPC）
每个 MCPLocalClient 对应一个 MCP 服务器子进程
"""
import os
import sys
import json
import asyncio
import signal
from typing import Optional
from tools.mcp.protocols import (
    build_initialize,
    build_initialized_notification,
    build_tools_list,
    build_tools_call,
    parse_tools_call_response,
)
from tools.mcp.protocols.tool import MCPTool


class MCPLocalClient:
    """MCP 本地客户端 — 管理单个 MCP 子进程的生命周期与通信"""
    
    def __init__(self, server_id: str, command: list, env: dict = None, cwd: str = None):
        self.server_id = server_id
        self.command = command
        self.env = env or {}
        self.cwd = cwd
        self._process: Optional[asyncio.subprocess.Process] = None
        self._tools: list = []
        self._req_id = 2  # 1 used by initialize
        self._own_loop: Optional[asyncio.AbstractEventLoop] = None

    def __del__(self):
        self._process = None

    async def start(self) -> bool:
        """启动子进程并初始化连接（异步）"""
        print(f"📋 [MCPLocalClient:{self.server_id}] 开始启动流程...")
        print(f"📋 [MCPLocalClient:{self.server_id}] 命令: {' '.join(self.command)}")
        print(f"📋 [MCPLocalClient:{self.server_id}] 工作目录: {self.cwd}")
        
        merged_env = os.environ.copy()
        merged_env.update(self.env)
        merged_env["PYTHONUNBUFFERED"] = "1"
        merged_env = self._enrich_path(merged_env)
        
        import shutil
        use_shell = False
        resolved_cmd = list(self.command)
        
        if os.name == 'nt' and resolved_cmd:
            first_cmd = resolved_cmd[0]
            if first_cmd.lower() == 'npx':
                node_path = shutil.which('node') or r'C:\Program Files\nodejs\node.exe'
                npx_js = self._resolve_npx_on_windows()
                if npx_js != 'npx' and os.path.isfile(npx_js):
                    resolved_cmd = [node_path, npx_js] + resolved_cmd[1:]
                    use_shell = False
                    print(f"📋 [MCPLocalClient:{self.server_id}] 命令解析: npx → node 直接运行 JS: {resolved_cmd}")
                else:
                    use_shell = True
                    resolved_cmd = ' '.join(self.command)
                    print(f"📋 [MCPLocalClient:{self.server_id}] 命令解析: npx → shell 回退: {resolved_cmd}")
            else:
                full_path = shutil.which(first_cmd)
                if full_path:
                    if full_path.lower().endswith(('.cmd', '.bat')):
                        use_shell = True
                        resolved_cmd = ' '.join(self.command)
                    else:
                        resolved_cmd[0] = full_path
                else:
                    print(f"📋 [MCPLocalClient:{self.server_id}] ⚠️ 命令 '{first_cmd}' 未找到")
        
        print(f"📋 [MCPLocalClient:{self.server_id}] 启动子进程...")
        print(f"📋 [MCPLocalClient:{self.server_id}] 最终命令: {resolved_cmd}")
        
        # ★ 关键：stderr 重定向到 stdout，避免 Windows ProactorEventLoop 上
        #   单独读取 stderr 管道时 IOCP 操作无法在退出时完成的问题。
        #   stderr 日志会通过 _recv() 的 stdout 读取通道一并输出。
        self._process = await asyncio.create_subprocess_exec(
            *resolved_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=merged_env,
            cwd=self.cwd,
        )
        print(f"📋 [MCPLocalClient:{self.server_id}] ✅ 子进程已启动 (PID: {self._process.pid})")
        
        if 'npx' in ' '.join(self.command).lower():
            await asyncio.sleep(1.5)
        else:
            await asyncio.sleep(0.5)
        
        print(f"📋 [MCPLocalClient:{self.server_id}] 发送 initialize 请求...")
        await self._send(build_initialize())
        print(f"📋 [MCPLocalClient:{self.server_id}] ✅ initialize 已发送，等待响应...")
        
        response = await self._recv()
        if response:
            print(f"📋 [MCPLocalClient:{self.server_id}] ✅ 收到 initialize 响应")
            result = response.get("result", {})
            server_info = result.get("serverInfo", {})
            print(f"📋 [MCPLocalClient:{self.server_id}]   服务器信息: {server_info.get('name','?')} v{server_info.get('version','?')}")
            
            caps = result.get("capabilities", {})
            tools_provided = caps.get("tools", {})
            print(f"📋 [MCPLocalClient:{self.server_id}]   能力: tools={bool(tools_provided)}")
            
            print(f"📋 [MCPLocalClient:{self.server_id}] 发送 initialized 通知...")
            await self._send(build_initialized_notification())
            print(f"📋 [MCPLocalClient:{self.server_id}] ✅ initialized 已发送")
            await asyncio.sleep(0.5)
            
            print(f"📋 [MCPLocalClient:{self.server_id}] 发送 tools/list 请求...")
            await self._send(build_tools_list())
            print(f"📋 [MCPLocalClient:{self.server_id}] ✅ tools/list 已发送，等待响应...")
            
            tools_response = await self._recv()
            if tools_response:
                tools_result = tools_response.get("result", {})
                tools_list = tools_result.get("tools", [])
                print(f"📋 [MCPLocalClient:{self.server_id}] ✅ 获取到 {len(tools_list)} 个工具:")
                for t in tools_list:
                    print(f"    - {t['name']}: {t.get('description','')[:60]}")
                    mt = MCPTool(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("inputSchema", {})
                    )
                    self._tools.append(mt)
            else:
                print(f"📋 [MCPLocalClient:{self.server_id}] ⚠️ tools/list 无响应")
            
            if self._process.returncode is not None:
                print(f"📋 [MCPLocalClient:{self.server_id}] ❌ 进程已退出 (code={self._process.returncode})")
                return False
            
            print(f"📋 [MCPLocalClient:{self.server_id}] 启动完成 ✅")
            print(f"✅ MCP {self.server_id} 启动成功 ({len(self._tools)} 工具)")
            return True
        
        print(f"📋 [MCPLocalClient:{self.server_id}] ❌ initialize 无响应")
        return False
    
    async def _send(self, data: str):
        print(f"📤 [MCP→Server:{self.server_id}] {data[:300]}")
        if self._process and self._process.stdin:
            self._process.stdin.write((data + "\n").encode('utf-8'))
            await self._process.stdin.drain()
    
    async def _recv(self, timeout: float = 8.0) -> Optional[dict]:
        deadline = asyncio.get_event_loop().time() + timeout
        line_count = 0
        
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            
            try:
                line_bytes = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=min(remaining, 5.0)
                )
            except asyncio.TimeoutError:
                print(f"⏱️ MCP {self.server_id} _recv 超时 ({timeout}s)")
                if self._process and self._process.returncode is not None:
                    print(f"❌ MCP {self.server_id} 进程已退出 (code={self._process.returncode})")
                return None
            except Exception:
                return None
            
            if not line_bytes:
                return None
            
            stripped = line_bytes.decode('utf-8', errors='replace').strip()
            if not stripped:
                continue
            
            line_count += 1
            
            try:
                obj = json.loads(stripped)
                result_str = json.dumps(obj, ensure_ascii=False)[:500]
                print(f"📥 [Server→MCP:{self.server_id}] {result_str}")
                return obj
            except json.JSONDecodeError:
                print(f"📋 [MCP-Server:{self.server_id}] (stdout) {stripped[:200]}")
                continue
        
        print(f"⏱️ MCP {self.server_id} _recv 超时 ({timeout}s)，共读取 {line_count} 行")
        return None
    
    async def call_tool(self, name: str, arguments: dict) -> str:
        if not self._process or not self._process.stdout or not self._process.stdin:
            print(f"❌ MCP {self.server_id} 子进程已退出，工具 '{name}' 无法调用")
            print(f"⏳ MCP {self.server_id} 尝试重启...")
            try:
                if await self.start():
                    print(f"✅ MCP {self.server_id} 重启成功，继续调用工具 '{name}'")
                else:
                    return f"❌ 工具 {name} 调用失败: 服务器 {self.server_id} 已断开且无法重启"
            except Exception as e:
                return f"❌ 工具 {name} 调用失败: 服务器 {self.server_id} 已断开 ({e})"
        
        self._req_id += 1
        await self._send(build_tools_call(name, arguments, self._req_id))
        response = await self._recv()
        if response:
            if "error" in response:
                err = response["error"]
                print(f"❌ MCP {self.server_id} 工具 '{name}' 返回错误: {err.get('message', '')}")
                return parse_tools_call_response(response)
            if not response.get("result", {}).get("content"):
                print(f"⚠️ MCP {self.server_id} 工具 '{name}' 返回空内容")
            return parse_tools_call_response(response)
        print(f"❌ MCP {self.server_id} 工具 '{name}' 调用失败: 无响应")
        return f"❌ 工具 {name} 调用失败"
    
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

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.returncode is None
    
    async def cleanup(self):
        """清理：杀子进程"""
        if self._process:
            try:
                if os.name == 'nt':
                    self._process.terminate()
                else:
                    self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        
        print(f"⏹ MCP {self.server_id} 已停止")
    
    # ---- 同步兼容包装 ----
    def start_sync(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._own_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._own_loop)
                try:
                    return self._own_loop.run_until_complete(self.start())
                except Exception:
                    self._own_loop.close()
                    self._own_loop = None
                    raise
            else:
                self._own_loop = loop
                return loop.run_until_complete(self.start())
        except RuntimeError:
            self._own_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._own_loop)
            try:
                return self._own_loop.run_until_complete(self.start())
            except Exception:
                self._own_loop.close()
                self._own_loop = None
                raise
        except Exception:
            if self._own_loop:
                try:
                    self._own_loop.close()
                except Exception:
                    pass
                self._own_loop = None
            raise
    
    def call_tool_sync(self, name: str, arguments: dict) -> str:
        loop = self._own_loop
        if loop is None or loop.is_closed():
            print(f"⚠️ [MCP:{self.server_id}] 事件循环已关闭，尝试创建新循环")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._own_loop = loop
        
        try:
            return loop.run_until_complete(self.call_tool(name, arguments))
        except RuntimeError:
            print(f"⚠️ [MCP:{self.server_id}] 事件循环不可用，创建临时循环")
            temp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(temp_loop)
            try:
                return temp_loop.run_until_complete(self.call_tool(name, arguments))
            finally:
                temp_loop.close()
    
    def cleanup_sync(self):
        """同步清理：杀进程 → 关循环"""
        loop = self._own_loop
        if loop and not loop.is_closed():
            try:
                loop.run_until_complete(self.cleanup())
            except RuntimeError:
                pass
            try:
                loop.close()
            except Exception:
                pass
        else:
            try:
                asyncio.run(self.cleanup())
            except RuntimeError:
                pass
        
        self._process = None
        self._own_loop = None
    
    # ---- 静态辅助方法 ----
    @staticmethod
    def _enrich_path(env: dict) -> dict:
        if os.name != 'nt':
            return env
        path = env.get('PATH', '')
        added = set()
        import shutil
        for cmd in ['node', 'npx', 'npm', 'pnpm', 'yarn', 'python', 'pip', 'uv', 'uvx', 'pipx']:
            try:
                cmd_path = shutil.which(cmd)
                if cmd_path:
                    cmd_dir = os.path.dirname(os.path.normpath(cmd_path))
                    if cmd_dir not in path and cmd_dir not in added:
                        path = cmd_dir + os.pathsep + path
                        added.add(cmd_dir)
            except Exception:
                pass
        scripts_dir = os.path.join(os.path.dirname(sys.executable), 'Scripts')
        if scripts_dir not in path and os.path.isdir(scripts_dir):
            path = scripts_dir + os.pathsep + path
        user_bin = os.path.expanduser(r'~\AppData\Roaming\npm')
        if user_bin not in path and os.path.isdir(user_bin):
            path = user_bin + os.pathsep + path
        env['PATH'] = path
        return env
    
    @staticmethod
    def _resolve_npx_on_windows() -> str:
        import shutil
        npx_path = shutil.which('npx')
        if not npx_path:
            return 'npx'
        npx_path = os.path.normpath(npx_path)
        bin_dir = os.path.dirname(npx_path)
        candidates = [
            os.path.join(bin_dir, 'node_modules', 'npm', 'bin', 'npx-cli.js'),
            os.path.join(os.path.expanduser(r'~\AppData\Roaming\npm'), 'node_modules', 'npm', 'bin', 'npx-cli.js'),
        ]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return 'npx'