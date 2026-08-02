"""
MCPBridge - MCP 服务桥接层
统一管理 MCP 服务器的生命周期、工具注册、工具执行、市场管理
连接前端 JS ↔ MCP Manager ↔ MCP Host（子进程）
"""
import json
import os
import re
import time
import urllib.request
from datetime import datetime
from PyQt5.QtCore import pyqtSlot, pyqtSignal

from .base import BridgeBase


def _read_json_file(path):
    """安全读取 JSON 文件"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


class MCPBridge(BridgeBase):
    """MCP 桥接 — 处理 MCP 服务器的前后端交互"""

    GITHUB_API_ISSUES = "https://api.github.com/repos/cline/mcp-marketplace/issues"

    _js_exec_signal = pyqtSignal(str)

    def __init__(self, app_controller):
        super().__init__(app_controller)
        self._js_exec_signal.connect(self._execute_js_safe)
        self._cached_market_items = []
        self._log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "mcp")
        os.makedirs(self._log_dir, exist_ok=True)
        self._log_paths: dict = {}  # item_id → log file path
        
        # 注册 MCPHost 状态变化回调 — 推模式，不轮询
        from tools.mcp.host import MCPHost
        def _on_mcp_status():
            self.execute_js("loadMCPServers();")
        MCPHost.on_status_change(_on_mcp_status)

    def _get_log_path(self, item_id: str) -> str:
        """获取日志文件路径。优先使用注册的自定义路径，否则使用默认日志目录"""
        if item_id in self._log_paths:
            return self._log_paths[item_id]
        return os.path.join(self._log_dir, f"{item_id}.log")

    def _register_log_path(self, item_id: str, server_dir: str, server_name: str = None):
        """注册日志路径到 MCP 服务器下载目录，文件名: {id}_{创建时间}.log"""
        try:
            t_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            name_part = (server_name or item_id).replace(' ', '_')
            log_file = os.path.join(server_dir, f"{name_part}_{t_str}.log")
            self._log_paths[item_id] = log_file
        except Exception:
            self._log_paths.pop(item_id, None)

    def _write_log(self, item_id: str, line: str):
        try:
            log_file = self._get_log_path(item_id)
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        except Exception:
            pass

    def _clear_log(self, item_id: str):
        try:
            log_file = self._get_log_path(item_id)
            if os.path.exists(log_file):
                os.remove(log_file)
        except Exception:
            pass

    @pyqtSlot(str, result=str)
    def getMCPLog(self, item_id: str):
        try:
            log_file = self._get_log_path(item_id)
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    return f.read()
            return ""
        except Exception:
            return ""

    def _js_log(self, server_id: str, msg: str):
        safe_msg = msg.replace("'", "\\'")
        self.execute_js(f"mcpAppendLog('{server_id}', '{safe_msg}');")
        print(f"[MCPBridge] {msg}")
        self._write_log(server_id, msg)

    def execute_js(self, js_code: str):
        self._js_exec_signal.emit(js_code)

    def _execute_js_safe(self, js_code: str):
        try:
            if self.app_controller and self.app_controller.webview:
                self.app_controller.webview.page().runJavaScript(js_code)
        except Exception as e:
            print(f"[MCPBridge] ❌ JS 执行失败: {e}")

    @pyqtSlot(str, result=str)
    def read_mcp_file(self, filename):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        filepath = os.path.join(base_dir, "mcp_server", filename)
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            print(f"读取 MCP 文件失败: {e}")
        return ""

    @pyqtSlot(str, str)
    def write_mcp_file(self, filename, content):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        filepath = os.path.join(base_dir, "mcp_server", filename)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"写入 MCP 文件失败: {e}")

    @pyqtSlot(str, str)
    def on_mcp_plugin_action(self, action, plugin_id):
        print(f"🔌 MCP 插件动作: {action} -> {plugin_id}")
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            if action == "install":
                mgr.register_client(plugin_id)
            elif action == "uninstall":
                mgr.uninstall_plugin(plugin_id)
        except Exception as e:
            print(f"❌ MCP 插件动作处理失败: {e}")

    @pyqtSlot(str, str)
    def installMCP(self, item_id, cmd):
        self._run_mcp_cmd(item_id, cmd, "install")

    @pyqtSlot(str, str)
    def uninstallMCP(self, item_id, cmd):
        self._run_mcp_cmd(item_id, cmd, "uninstall")

    def _run_mcp_cmd(self, item_id, cmd, action):
        import threading, subprocess
        def worker():
            try:
                print(f"[MCP] {action} {item_id}: {cmd}")
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in iter(process.stdout.readline, ""):
                    if line:
                        line_safe = line.replace("'", "\\'").replace("\n", " ").replace("\r", "")
                        self.execute_js(f"mcpAppendLog('{item_id}', '{line_safe}');")
                process.stdout.close()
                return_code = process.wait()
                self.execute_js(f"mcpFinishInstall('{item_id}', {return_code});")
                print(f"[MCP] {action} 完成: {item_id}, code={return_code}")
            except Exception as e:
                print(f"[MCP] {action} 失败: {e}")
                self.execute_js(f"mcpAppendLog('{item_id}', '错误: {str(e).replace(chr(39), '')}');")
                self.execute_js(f"mcpFinishInstall('{item_id}', -1);")
        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str, result=str)
    def refreshMarketFromUrl(self, url):
        import json as json_mod, urllib.request, re, time
        try:
            headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html,application/json,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9', 'Cache-Control': 'no-cache'}
            html = None
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        html = resp.read().decode("utf-8", errors="replace")
                    break
                except Exception:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise
            if not html:
                return json_mod.dumps({"error": "无法获取页面内容"})
            results = []
            seen = set()
            cards = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>([^<]{2,80})</a>', html)
            for link, name in cards:
                name = name.strip()
                if not name or len(name) > 80:
                    continue
                item_id = name.lower().replace(" ", "-").replace("/", "-")
                if item_id in seen:
                    continue
                seen.add(item_id)
                results.append({"id": item_id, "name": name, "description": f"MCP 服务器: {name}", "downloads": 0, "stars": 0, "installed": False, "installCommand": f"npm install -g @modelcontextprotocol/server-{item_id}", "uninstallCommand": f"npm uninstall -g @modelcontextprotocol/server-{item_id}"})
            return json_mod.dumps(results, ensure_ascii=False)
        except Exception as e:
            return json_mod.dumps({"error": str(e)})

    def _register_mcp_tools_to_ai(self, server_id: str, host):
        self._js_log(server_id, "🔄 正在握手获取工具列表...")
        try:
            ai_client = getattr(self.app_controller, 'ai_client', None)
            if ai_client and hasattr(ai_client, 'register_mcp_handler'):
                if hasattr(self.app_controller, 'mcp_dispatcher'):
                    mcp_disp = self.app_controller.mcp_dispatcher
                    client = host._clients.get(server_id) if hasattr(host, '_clients') else None
                    if not client:
                        client = host
                    if hasattr(client, 'list_tools'):
                        tools_list = client.list_tools()
                        tool_names = []
                        for t in tools_list:
                            tool_name = t.name
                            tool_names.append(tool_name)
                            async def make_handler(args_dict, tn=tool_name, cl=client):
                                args_dict = args_dict or {}
                                return cl.call_tool(tn, args_dict)
                            mcp_disp.register(tool_name, make_handler)
                            self._js_log(server_id, f"📌 MCP 工具已注册: {tool_name}")
                        if tool_names:
                            self._js_log(server_id, f"✅ 共注册 {len(tool_names)} 个工具: {', '.join(tool_names)}")
                        else:
                            self._js_log(server_id, "⚠️ 该服务器未提供任何工具")
                    else:
                        self._js_log(server_id, "⚠️ 服务器无 list_tools 方法")
                else:
                    self._js_log(server_id, "⚠️ 系统中无 MCPDispatcher")
                ai_client.register_mcp_handler()
                self._js_log(server_id, "✅ AI 客户端已接收 MCP 工具更新")
            else:
                self._js_log(server_id, "⚠️ AI 客户端未就绪，跳过注入")
        except Exception as e:
            self._js_log(server_id, f"❌ 注册 MCP 工具到 AI 失败: {str(e)[:100]}")

    @pyqtSlot(str, result=bool)
    def startMCPServer(self, server_id: str):
        self._js_log(server_id, "🔄 正在启动服务器...")
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = mgr._read_config()
            servers = config.get("mcpServers", {})
            cfg = servers.get(server_id)
            if not cfg:
                self._js_log(server_id, "❌ 配置不存在，启动失败")
                return False
            transport = cfg.get("transport", "unknown")
            cmd = cfg.get("command", "")
            args = cfg.get("args", [])
            cwd = cfg.get("cwd", "")
            self._js_log(server_id, f"📋 配置: transport={transport}")
            self._js_log(server_id, f"📋 命令: {cmd} {' '.join(args)}")
            self._js_log(server_id, f"📋 工作目录: {cwd}")
            import os as _os
            if cwd and not _os.path.isdir(cwd):
                self._js_log(server_id, f"⚠️ 工作目录不存在: {cwd}")
            if transport == "stdio":
                import shutil
                cmd_path = cmd.split()[0] if isinstance(cmd, str) else cmd[0] if isinstance(cmd, list) else str(cmd)
                found_cmd = shutil.which(cmd_path) if shutil.which(cmd_path) else cmd_path
                self._js_log(server_id, f"📋 命令路径: {found_cmd}")
            self._js_log(server_id, "📝 已更新配置，正在注册客户端...")
            cfg["enabled"] = True
            servers[server_id] = cfg
            mgr._write_config(config)
            if mgr.register_client(server_id, cfg):
                client = mgr._clients.get(server_id)
                if client:
                    tools = client.list_tools()
                    tool_names = [t.name for t in tools]
                    self._js_log(server_id, f"✅ 启动成功，发现 {len(tool_names)} 个工具: {', '.join(tool_names)}")
                    self._register_mcp_tools_to_ai(server_id, mgr)
                else:
                        self._js_log(server_id, "⚠️ 注册成功但未能获取客户端句柄")
                self.execute_js(f"mcpFinishInstall('{server_id}', 0);")
                self.execute_js("loadMCPServers();")
                return True
            else:
                self._js_log(server_id, "❌ register_client 返回 false")
                try:
                    import subprocess
                    cmd_full = [cmd] + args if isinstance(cmd, str) else list(cmd) + list(args)
                    proc = subprocess.Popen(cmd_full, cwd=cwd if _os.path.isdir(cwd) else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        stdout, stderr = proc.communicate(timeout=3)
                        self._js_log(server_id, f"📋 测试运行 stdout: {stdout[:200]}")
                        self._js_log(server_id, f"📋 测试运行 stderr: {stderr[:200]}")
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        self._js_log(server_id, "⏱️ 命令运行超时（可能正常，是长久运行的服务器进程）")
                except Exception as run_err:
                    self._js_log(server_id, f"❌ 测试运行失败: {str(run_err)[:80]}")
                return False
        except Exception as e:
            self._js_log(server_id, f"❌ 启动异常: {str(e)[:100]}")
            return False

    @pyqtSlot(str, result=bool)
    def stopMCPServer(self, server_id: str):
        self._js_log(server_id, "🛑 正在停止服务器...")
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            mgr.unregister_client(server_id)
            config = mgr._read_config()
            servers = config.setdefault("mcpServers", {})
            if server_id in servers:
                servers[server_id]["enabled"] = False
                mgr._write_config(config)
            self._js_log(server_id, "✅ 服务器已停止")
            self.execute_js("loadMCPServers();")
            return True
        except Exception as e:
            self._js_log(server_id, f"❌ 停止失败: {str(e)[:100]}")
            return False

    @pyqtSlot(str, result=bool)
    def restartMCPServer(self, server_id: str):
        self._js_log(server_id, "🔄 正在重启服务器...")
        try:
            self._js_log(server_id, "🛑 先停止...")
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            mgr.unregister_client(server_id)
            config = mgr._read_config()
            servers = config.get("mcpServers", {})
            cfg = servers.get(server_id)
            if cfg:
                cfg["enabled"] = True
                self._js_log(server_id, "▶️ 正在启动...")
                result = mgr.register_client(server_id, cfg)
                if result:
                    client = mgr._clients.get(server_id)
                    if client:
                        tools = client.list_tools()
                        tool_names = [t.name for t in tools]
                        self._js_log(server_id, f"✅ 重启成功，工具: {', '.join(tool_names)}")
                    self._register_mcp_tools_to_ai(server_id, mgr)
                else:
                    self._js_log(server_id, "❌ 重启失败")
                self.execute_js("loadMCPServers();")
                return result
            self._js_log(server_id, "❌ 配置不存在")
            return False
        except Exception as e:
            self._js_log(server_id, f"❌ 重启异常: {str(e)[:100]}")
            return False

    @pyqtSlot(str, result=str)
    def getServerStatus(self, server_id: str):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            client = mgr._clients.get(server_id)
            if client and client.is_running():
                tools = client.list_tools()
                return json.dumps({"online": True, "tools": [{"name": t.name, "description": t.description} for t in tools], "toolCount": len(tools)}, ensure_ascii=False)
            else:
                return json.dumps({"online": False, "tools": [], "toolCount": 0})
        except Exception as e:
            return json.dumps({"online": False, "tools": [], "error": str(e)})

    @pyqtSlot(result=str)
    def getAllServersStatus(self):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            result = []
            for sid, client in mgr._clients.items():
                tools = []
                tool_count = 0
                running = client.is_running()
                if running:
                    try:
                        tools_list = client.list_tools()
                        tools = [{"name": t.name, "description": t.description} for t in tools_list]
                        tool_count = len(tools)
                    except Exception:
                        pass
                result.append({"id": sid, "online": running, "tools": tools, "toolCount": tool_count})
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            print(f"[MCPBridge] ❌ getAllServersStatus 失败: {e}")
            return "[]"

    def _notify_mcp_status(self):
        """触发前端更新 MCP 状态徽标（后台启动完成/单个服务器上线时调用）"""
        try:
            self.execute_js("if(typeof updateMCPBadge==='function')updateMCPBadge();"
                            "if(typeof renderMCPLocalServers==='function')renderMCPLocalServers();")
        except Exception:
            pass
    
    @pyqtSlot(result=str)
    def getMCPServers(self):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            servers = mgr.get_all_servers()
            online_count = sum(1 for s in servers if s.get("online"))
            print(f"[MCPBridge] 🔍 getMCPServers: {len(servers)} 个服务器 ({online_count} 在线)")
            for s in servers:
                sid = s["id"]
                client = mgr._clients.get(sid)
                if client and client.is_running():
                    try:
                        tools = client.list_tools()
                        s["tools"] = [{"name": t.name, "description": t.description} for t in tools]
                        s["toolCount"] = len(tools)
                    except Exception:
                        s["tools"] = []
                        s["toolCount"] = 0
                else:
                    s["tools"] = []
                    s["toolCount"] = 0
            result = json.dumps(servers, ensure_ascii=False)
            print(f"[MCPBridge] ✅ getMCPServers 返回 JSON (长度 {len(result)} 字符)")
            return result
        except Exception as e:
            print(f"[MCPBridge] ❌ getMCPServers 失败: {e}")
            import traceback
            traceback.print_exc()
            return "[]"

    @pyqtSlot(str, result=str)
    def getMCPTools(self):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            tools = mgr.get_tools()
            return json.dumps(tools, ensure_ascii=False)
        except Exception as e:
            print(f"[MCPBridge] ❌ getMCPTools 失败: {e}")
            return "[]"

    @pyqtSlot(str, result=str)
    def getMCPToolList(self, server_id: str):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            host = mgr._clients.get(server_id)
            if host:
                tools = host.list_tools()
                result = [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]
                return json.dumps(result, ensure_ascii=False)
            return "[]"
        except Exception as e:
            print(f"[MCPBridge] ❌ getMCPToolList 失败: {e}")
            return "[]"

    @pyqtSlot(str, str, str, result=bool)
    def addMCPServer(self, server_id: str, name: str, url: str, description: str = ""):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            mgr.add_remote_server(server_id, url)
            config = mgr._read_config()
            servers = config.setdefault("mcpServers", {})
            if server_id in servers:
                servers[server_id]["description"] = description or f"{name} 远程服务"
                servers[server_id]["name"] = name
                mgr._write_config(config)
            print(f"[MCPBridge] ✅ 已添加 MCP 服务器: {server_id} ({url})")
            return True
        except Exception as e:
            print(f"[MCPBridge] ❌ addMCPServer 失败: {e}")
            return False

    @pyqtSlot(str, result=bool)
    def removeMCPServer(self, server_id: str):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            mgr.remove_remote_server(server_id)
            print(f"[MCPBridge] ✅ 已删除 MCP 服务器: {server_id}")
            return True
        except Exception as e:
            print(f"[MCPBridge] ❌ removeMCPServer 失败: {e}")
            return False

    @pyqtSlot(result=str)
    def getMCPConfig(self):
        print(f"[MCPBridge] 🔍 getMCPConfig 被调用")
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = mgr._read_config()
            server_count = len(config.get("mcpServers", {}))
            print(f"[MCPBridge]    config 中有 {server_count} 个服务器")
            return json.dumps(config, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[MCPBridge] ❌ getMCPConfig 失败: {e}")
            return "{}"

    @pyqtSlot(str, result=bool)
    def saveMCPConfig(self, config_json: str):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = json.loads(config_json)
            old_config = mgr._read_config()
            old_servers = old_config.get("mcpServers", {})
            new_servers = config.get("mcpServers", {})
            
            # ===== 智能更新：只重启有变动的服务器 =====
            to_stop = set()
            to_start = []
            
            # 找出需要停止的：在运行中但配置有变化或已删除的
            for sid in list(mgr._clients.keys()):
                if sid not in new_servers:
                    to_stop.add(sid)
                elif old_servers.get(sid) != new_servers.get(sid):
                    to_stop.add(sid)
            
            # 找出需要启动的：新配置中有但不在运行中的（包括之前停了的）
            for sid, cfg in new_servers.items():
                if cfg.get("enabled", True) and sid not in mgr._clients:
                    to_start.append((sid, cfg))
            
            self._js_log("_config", f"🔄 saveMCPConfig: 准备停止 {len(to_stop)} 个, 重启/新增 {len(new_servers)} 个中的...")
            
            # 停止有变动的服务器
            for sid in to_stop:
                self._js_log(sid, "🛑 配置变更，停止旧服务器...")
                mgr.unregister_client(sid)
                self._js_log(sid, "✅ 已停止")
            
            # 保存新配置
            mgr._write_config(config)
            self._js_log("_config", "✅ 配置已保存到文件")
            
            # 在停止之后重新计算需要启动的：新配置中有且未在运行中（包括刚停了的）的
            started = 0
            for sid, cfg in new_servers.items():
                if cfg.get("enabled", True) and sid not in mgr._clients:
                    self._js_log(sid, "▶️ 正在启动服务器...")
                    if mgr.register_client(sid, cfg):
                        self._js_log(sid, "✅ 启动成功")
                        started += 1
                    else:
                        self._js_log(sid, "❌ 启动失败")
                elif cfg.get("enabled", True) and sid in to_stop:
                    # 已停止的服务器需要在停止后启动
                    self._js_log(sid, "▶️ 重新启动服务器...")
                    if mgr.register_client(sid, cfg):
                        self._js_log(sid, "✅ 启动成功")
                        started += 1
                    else:
                        self._js_log(sid, "❌ 启动失败")
            
            self._js_log("_config", f"✅ MCP 配置增量更新完成（启动了 {started} 个服务器）")
            return True
        except Exception as e:
            print(f"[MCPBridge] ❌ saveMCPConfig 失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def execute_tool_async(self, tool_name: str, arguments: dict) -> str:
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            handler = mgr._tool_handlers.get(tool_name)
            if handler:
                try:
                    return handler(arguments)
                except Exception as e:
                    return f"❌ 工具 '{tool_name}' 执行失败: {str(e)}"
            for host in mgr._clients.values():
                for t in host.list_tools():
                    if t.name == tool_name:
                        print(f"[MCPBridge] 🔍 在 {host.server_id} 中找到工具 '{tool_name}'")
                        result = host.call_tool(tool_name, arguments)
                        return result
            return f"⚠️ MCP 工具 '{tool_name}' 未找到对应处理器"
        except Exception as e:
            print(f"[MCPBridge] ❌ execute_tool 失败: {e}")

    @pyqtSlot(result=str)
    def getMCPStatus(self):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            status = []
            for sid, host in mgr._hosts.items():
                status.append({"id": sid, "running": host.is_running(), "tools_count": len(host.list_tools())})
            return json.dumps(status, ensure_ascii=False)
        except Exception as e:
            print(f"[MCPBridge] ❌ getMCPStatus 失败: {e}")
            return "[]"

    @pyqtSlot(result=bool)
    def startAllMCPServers(self):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = mgr._read_config()
            servers = config.get("mcpServers", {})
            success = True
            for sid, cfg in servers.items():
                if cfg.get("enabled", True) and sid not in mgr._hosts:
                    if not mgr.register_client(sid, cfg):
                        success = False
                    else:
                        self._register_mcp_tools_to_ai(sid, mgr)
            self.execute_js("loadMCPServers();")
            return success
        except Exception as e:
            print(f"[MCPBridge] ❌ startAllMCPServers 失败: {e}")
            return False

    @pyqtSlot(result=bool)
    def stopAllMCPServers(self):
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            mgr.stop_all()
            self.execute_js("loadMCPServers();")
            return True
        except Exception as e:
            print(f"[MCPBridge] ❌ stopAllMCPServers 失败: {e}")
            return False

    def _parse_issue_to_market_item(self, issue: dict) -> dict:
        title = issue.get("title", "") or ""
        body = issue.get("body", "") or ""
        number = issue.get("number", 0)
        if not title.startswith("[Server Submission]"):
            return None
        server_name = title.replace("[Server Submission]: ", "").strip()
        if not server_name:
            return None
        safe_id = f"mcp-{number}"
        repo_match = re.search(r'### GitHub Repository URL\s*\n\s*(https?://github\.com[^\s\n]+)', body, re.IGNORECASE | re.MULTILINE)
        repo_url = repo_match.group(1).strip() if repo_match else ""
        logo_match = re.search(r'### Logo Image\s*\n\s*(https?://[^\s\n]+)', body, re.IGNORECASE | re.MULTILINE)
        logo_url = logo_match.group(1).strip() if logo_match else ""
        desc_match = re.search(r'### Additional Information\s*\n\s*(.+?)(?:\n###\s|\Z)', body, re.IGNORECASE | re.DOTALL)
        description = desc_match.group(1).strip()[:500] if desc_match else ""
        if not description:
            lines = [l.strip() for l in body.split('\n') if l.strip() and not l.startswith('#') and not l.startswith('-')]
            description = ' '.join(lines[:5])[:300]
        author = issue.get("user", {}).get("login", "unknown")
        has_been_tested = False
        if '### Installation Testing' in body:
            idx = body.index('### Installation Testing')
            has_been_tested = '[x]' in body[idx:idx+300]
        body_lower = body.lower()
        is_remote = 'streamable-http' in body_lower or 'streamable http' in body_lower or 'remote' in body_lower[:600] or '### remotes' in body_lower
        is_local = bool(repo_url) and not is_remote
        server_type = 'remote' if is_remote else ('local' if is_local else 'unknown')
        return {"id": safe_id, "name": server_name, "title": server_name, "githubRepoUrl": repo_url, "logo": logo_url, "description": description, "author": author, "issueNumber": number, "installed": False, "tested": has_been_tested, "serverType": server_type, "labels": [l["name"] for l in issue.get("labels", [])], "createdAt": issue.get("created_at", "")}

    def _fetch_github_issues(self, url: str, max_pages: int = 5) -> list:
        import urllib.request, re as _re
        all_issues = []
        page_url = url
        self._js_log("market", "📡 正在从 GitHub API 获取数据...")
        for page in range(max_pages):
            try:
                self._js_log("market", f"📥 请求第 {page+1} 页: {page_url[:80]}...")
                req = urllib.request.Request(page_url, headers={'User-Agent': 'Agent-MCP/1.0', 'Accept': 'application/vnd.github.v3+json'})
                link_header = ""
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw_data = b""
                    chunk_count = 0
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        raw_data += chunk
                        chunk_count += 1
                    issues = json.loads(raw_data)
                    self._js_log("market", f"✅ 第 {page+1} 页获取完成，共 {len(issues)} 条 (读取 {chunk_count} 个数据块)")
                    if not issues:
                        self._js_log("market", "📭 该页无数据，停止分页")
                        break
                    all_issues.extend(issues)
                    link_header = resp.headers.get('Link', '')
                if 'next' not in link_header:
                    self._js_log("market", "📄 无下一页，分页结束")
                    break
                next_match = _re.search(r'<([^>]+)>;\s*rel="next"', link_header)
                if next_match:
                    page_url = next_match.group(1)
                    self._js_log("market", "➡️ 继续下一页...")
                else:
                    break
            except Exception as e:
                self._js_log("market", f"⚠️ GitHub 分页 {page+1} 获取失败: {str(e)[:60]}")
                break
        self._js_log("market", f"📊 GitHub 数据拉取完成，共获取 {len(all_issues)} 条 Issues")
        return all_issues

    @pyqtSlot(result=str)
    def getMCPMarket(self):
        try:
            from storage.repositories.mcp_market_repo import MCPMarketRepository
            repo = MCPMarketRepository()
            count = repo.count()
            if count > 0:
                items = repo.get_all()
                try:
                    from tools.mcp.host import MCPHost
                    mgr = MCPHost()
                    config = mgr._read_config()
                    local_servers = config.get("mcpServers", {})
                    for item in items:
                        if item["id"] in local_servers:
                            item["installed"] = True
                            # 同步到数据库持久化
                            repo.upsert(item)
                except Exception:
                    pass
                print(f"[MCPBridge] ✅ 从本地数据库加载 {len(items)} 个市场项")
                return json.dumps({"market": items}, ensure_ascii=False)
            else:
                print(f"[MCPBridge] ℹ️ 本地数据库无市场数据，返回空列表")
                return json.dumps({"market": []})
        except Exception as e:
            print(f"[MCPBridge] ❌ 读取市场数据库失败: {e}")
            return json.dumps({"market": []})

    @pyqtSlot()
    def refreshMCPMarket(self):
        import threading
        self._js_log("market", "🔄 正在从 GitHub 刷新 MCP 市场数据...")
        self.execute_js("window._onMCPRefreshStarted();")
        threading.Thread(target=self._refresh_market_worker, daemon=True).start()

    def _refresh_market_worker(self):
        import json as json_mod
        all_issues = []
        try:
            self._js_log("market", "🔍 获取 open 状态的 Issues...")
            open_url = f"{self.GITHUB_API_ISSUES}?state=open&per_page=100&sort=created&direction=desc"
            open_issues = self._fetch_github_issues(open_url, max_pages=5)
            all_issues.extend(open_issues)
        except Exception as e:
            self._js_log("market", f"⚠️ 获取 open Issues 失败: {str(e)[:60]}")
        try:
            self._js_log("market", "🔍 获取 closed+approved 状态的 Issues...")
            closed_url = f"{self.GITHUB_API_ISSUES}?state=closed&per_page=100&sort=created&direction=desc&labels=approved"
            closed_issues = self._fetch_github_issues(closed_url, max_pages=5)
            all_issues.extend(closed_issues)
        except Exception as e:
            self._js_log("market", f"⚠️ 获取 closed Issues 失败: {str(e)[:60]}")
        seen_numbers = set()
        items = []
        cached = []
        for issue in all_issues:
            number = issue.get("number", 0)
            if number in seen_numbers:
                continue
            seen_numbers.add(number)
            parsed = self._parse_issue_to_market_item(issue)
            if parsed:
                full_item = {**parsed, "raw_issue": {"url": issue.get("html_url", ""), "number": issue.get("number", 0), "title": issue.get("title", ""), "state": issue.get("state", "open"), "body": issue.get("body", ""), "labels": [{"name": l["name"], "color": l.get("color", "")} for l in issue.get("labels", [])], "user": issue.get("user", {}), "created_at": issue.get("created_at", ""), "updated_at": issue.get("updated_at", ""), "comments_url": issue.get("comments_url", ""), "comments": issue.get("comments", 0)}}
                items.append(full_item)
                cached.append({"id": full_item["id"], "name": full_item["name"], "githubRepoUrl": full_item["githubRepoUrl"]})
        self._cached_market_items = cached
        try:
            from storage.repositories.mcp_market_repo import MCPMarketRepository
            repo = MCPMarketRepository()
            repo.upsert_many(items)
            self._js_log("market", f"💾 已保存 {len(items)} 条市场数据到数据库")
        except Exception as e:
            self._js_log("market", f"⚠️ 保存到数据库失败: {str(e)[:60]}")
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = mgr._read_config()
            local_servers = config.get("mcpServers", {})
            for item in items:
                if item["id"] in local_servers:
                    item["installed"] = True
                    # 同步 installed 到数据库持久化
                    try:
                        from storage.repositories.mcp_market_repo import MCPMarketRepository
                        _repo = MCPMarketRepository()
                        _repo.upsert(item)
                    except Exception:
                        pass
        except Exception:
            pass
        print(f"[MCPBridge] ✅ 从 GitHub 刷新 {len(items)} 个市场项并保存到数据库")
        result_json = json_mod.dumps({"market": items}, ensure_ascii=False)
        safe_result = json_mod.dumps(result_json)
        self.execute_js(f"window._onMCPMarketRefreshed({safe_result});")

    def _get_market_item(self, item_id: str) -> dict:
        for citem in self._cached_market_items:
            if citem.get("id") == item_id:
                return citem
        try:
            from storage.repositories.mcp_market_repo import MCPMarketRepository
            repo = MCPMarketRepository()
            return repo.get_by_id(item_id)
        except Exception:
            return {}

    def _run_subprocess_with_log(self, item_id: str, cmd: str, action: str, timeout: int = 120):
        """运行子进程并实时输出日志，支持超时和自动重试"""
        import subprocess
        import threading as _threading
        import queue
        import time as _time
        
        self._write_log(item_id, f"🔄 {action}: {cmd}")
        for attempt in range(2):  # 失败后自动重试 1 次
            if attempt > 0:
                self.execute_js(f"mcpAppendLog('{item_id}', '🔄 重试第 {attempt+1} 次...');")
                _time.sleep(2)
            try:
                cmd_safe = cmd.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace("\r", "")
                self.execute_js(f"mcpAppendLog('{item_id}', '$ {cmd_safe}');")
                print(f"[MCPBridge] {action} {item_id}: {cmd}")
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0)
                q = queue.Queue()
                def reader():
                    try:
                        buf = ""
                        while True:
                            char = process.stdout.read(1)
                            if not char: break
                            if char == '\n': q.put(buf); buf = ""
                            elif char == '\r': 
                                if buf: q.put(buf); buf = ""
                            else: buf += char
                        if buf: q.put(buf)
                    except Exception: pass
                    finally: q.put(None)
                r_thread = _threading.Thread(target=reader, daemon=True)
                r_thread.start()
                
                # 带超时的读取循环
                deadline = _time.time() + timeout
                while _time.time() < deadline:
                    try:
                        line = q.get(timeout=1)
                        if line is None: break
                        if line:
                            line_safe = line.replace("'", "\\'")
                            self.execute_js(f"mcpAppendLog('{item_id}', '{line_safe}');")
                            self._write_log(item_id, line)
                    except queue.Empty:
                        # 检查进程是否还活着
                        if process.poll() is not None:
                            # 进程已退出，清空剩余输出
                            break
                        continue
                else:
                    # 超时 - 杀掉进程
                    self.execute_js(f"mcpAppendLog('{item_id}', '⏱️ 命令超时 ({timeout}s)，强制终止');")
                    try:
                        process.kill()
                    except Exception:
                        pass
                    if attempt < 1:
                        continue  # 重试
                    self.execute_js(f"mcpFinishInstall('{item_id}', -1);")
                    return -1
                
                r_thread.join(timeout=2)
                process.stdout.close()
                return_code = process.wait()
                if return_code == 0:
                    self.execute_js(f"mcpFinishInstall('{item_id}', 0);")
                    self._write_log(item_id, f"✅ {action} 完成 (code={return_code})")
                    print(f"[MCPBridge] ✅ {action} 完成: {item_id}, code={return_code}")
                    return 0
                else:
                    self.execute_js(f"mcpAppendLog('{item_id}', '⚠️ {action} 返回 code={return_code}');")
                    if attempt < 1:
                        self.execute_js(f"mcpAppendLog('{item_id}', '🔄 准备重试...');")
                        continue  # 重试
                    self.execute_js(f"mcpFinishInstall('{item_id}', {return_code});")
                    self._write_log(item_id, f"❌ {action} 失败 (code={return_code})")
                    print(f"[MCPBridge] ❌ {action} 失败: {item_id}, code={return_code}")
                    return return_code
            except Exception as e:
                print(f"[MCPBridge] ❌ {action} 失败: {e}")
                if attempt < 1:
                    continue  # 重试
                err_msg = str(e).replace("'", "").replace("\\", "\\\\")
                self.execute_js(f"mcpAppendLog('{item_id}', '错误: {err_msg}');")
                self.execute_js(f"mcpFinishInstall('{item_id}', -1);")
                self._write_log(item_id, f"❌ {action} 失败: {e}")
                return -1

    def _auto_install_deps(self, item_id: str, clone_dir: str):
        """检测并自动安装项目依赖"""
        import subprocess
        import os
        
        # 检测包管理器
        if os.path.exists(os.path.join(clone_dir, "pnpm-workspace.yaml")) or os.path.exists(os.path.join(clone_dir, "pnpm-lock.yaml")):
            pm_cmd = "pnpm install"
            pm_name = "pnpm"
        elif os.path.exists(os.path.join(clone_dir, "yarn.lock")):
            pm_cmd = "yarn install"
            pm_name = "yarn"
        elif os.path.exists(os.path.join(clone_dir, "package.json")):
            pm_cmd = "npm install"
            pm_name = "npm"
        else:
            return  # 没有 package.json，跳过
        
        self.execute_js(f"mcpAppendLog('{item_id}', '📦 检测到 {pm_name} 项目，自动安装依赖...');")
        self._run_subprocess_with_log(item_id, pm_cmd, f"{pm_name} install", timeout=180)

    @pyqtSlot(str, str)
    def installMCPFromMarket(self, item_id: str, repo_url: str):
        """从市场安装 MCP 服务器 — git clone 后交 AI 分析"""
        import threading
        import time as _time
        def worker():
            start_time = _time.time()
            self._clear_log(item_id)
            self._write_log(item_id, f"📦 开始安装: {item_id}")
            self.execute_js(f"mcpAppendLog('{item_id}', '══════');")
            self.execute_js(f"mcpAppendLog('{item_id}', '📦 开始安装 MCP 服务器: {item_id}');")

            install_url = repo_url
            install_name = item_id
            if not install_url:
                market_item = self._get_market_item(item_id)
                install_url = market_item.get("githubRepoUrl", "")
                install_name = market_item.get("name", item_id)
            else:
                try:
                    from storage.repositories.mcp_market_repo import MCPMarketRepository
                    repo = MCPMarketRepository()
                    db_item = repo.get_by_id(item_id)
                    if db_item:
                        install_name = db_item.get("name", item_id) or item_id
                except Exception:
                    pass

            if not install_url:
                self.execute_js(f"mcpAppendLog('{item_id}', '❌ 未找到 GitHub 仓库 URL');")
                self.execute_js(f"mcpFinishInstall('{item_id}', -1);")
                self._write_log(item_id, "❌ 未找到 GitHub 仓库 URL")
                return

            repo_dir_name = install_url.rstrip('/').split('/')[-1] if install_url else item_id
            repo_dir_name = repo_dir_name.replace('.git', '').lower()

            self.execute_js(f"mcpAppendLog('{item_id}', '📌 名称: {install_name}');")
            self.execute_js(f"mcpAppendLog('{item_id}', '🔗 仓库: {install_url}');")
            t_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.execute_js(f"mcpAppendLog('{item_id}', '⏱️ 安装开始时间: {t_str}');")

            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            clone_dir = os.path.join(base, "tools", "mcp", "server", repo_dir_name)
            config_id = repo_dir_name
            self._write_log(item_id, f"🔗 配置 ID: {config_id}")
            self.execute_js(f"mcpAppendLog('{item_id}', '📁 目标目录: tools/mcp/server/{repo_dir_name}');")
            
            # 注册日志路径到服务器下载目录
            self._register_log_path(item_id, clone_dir, install_name)

            import shutil as _shutil
            if os.path.exists(base):
                try:
                    total, used, free = _shutil.disk_usage(base)
                    free_gb = free / (1024**3)
                    self.execute_js(f"mcpAppendLog('{item_id}', '💾 磁盘剩余空间: {free_gb:.1f} GB');")
                except Exception: pass

            self.execute_js(f"mcpAppendLog('{item_id}', '─' * 30);")
            self.execute_js(f"mcpAppendLog('{item_id}', '🔧 步骤 1/2: 获取源码');")
            self.execute_js(f"mcpAppendLog('{item_id}', '─' * 30);")
            t1 = _time.time()
            if not os.path.exists(clone_dir):
                self.execute_js(f"mcpAppendLog('{item_id}', '📥 正在克隆仓库（浅克隆 --depth 1）...');")
                self.execute_js(f"mcpAppendLog('{item_id}', '   源: {install_url}');")
                self.execute_js(f"mcpAppendLog('{item_id}', '   目标: {clone_dir}');")
                # 浅克隆：只取最新代码，减少下载量，避免网络超时
                clone_cmd = f"git clone --depth 1 \"{install_url}\" \"{clone_dir}\""
                clone_code = self._run_subprocess_with_log(item_id, clone_cmd, "克隆仓库", timeout=180)
                self.execute_js(f"mcpAppendLog('{item_id}', '   ⏱️ 克隆耗时: {_time.time()-t1:.1f}s');")
                # 克隆成功后，检查是否有依赖需要安装
                if clone_code == 0:
                    self._auto_install_deps(item_id, clone_dir)
            else:
                self.execute_js(f"mcpAppendLog('{item_id}', '📁 目录已存在，跳过克隆');")
                clone_code = 0

            if clone_code != 0:
                self.execute_js(f"mcpAppendLog('{item_id}', '❌ 仓库克隆失败，code={clone_code}');")
                self.execute_js(f"mcpAppendLog('{item_id}', '💡 请检查网络/Git 是否安装/仓库地址');")
                return

            if os.path.exists(clone_dir):
                try:
                    files = os.listdir(clone_dir)
                    file_count = len(files)
                    total_size = sum(os.path.getsize(os.path.join(clone_dir, f)) for f in files if os.path.isfile(os.path.join(clone_dir, f)))
                    self.execute_js(f"mcpAppendLog('{item_id}', '📂 目录内容: {file_count} 个文件/目录, 总大小: {total_size/1024:.1f} KB');")
                    self.execute_js(f"mcpAppendLog('{item_id}', '   文件列表: {', '.join(files[:10])}{'...' if len(files) > 10 else ''}');")
                except Exception: pass
            self.execute_js(f"mcpAppendLog('{item_id}', '✅ 源码获取成功');")

            self._install_context = {
                "item_id": item_id, "name": install_name, "repo_url": install_url,
                "clone_dir": clone_dir, "config_id": repo_dir_name, "start_time": start_time,
            }

            self.execute_js(f"mcpAppendLog('{item_id}', '');")
            self.execute_js(f"mcpAppendLog('{item_id}', '─' * 30);")
            self.execute_js(f"mcpAppendLog('{item_id}', '🔧 步骤 2/2: AI 智能分析');")
            self.execute_js(f"mcpAppendLog('{item_id}', '─' * 30);")
            # 传递绝对路径给前端
            abs_path = clone_dir.replace('\\', '\\\\')
            self.execute_js(f"mcpAppendLog('{item_id}', '🤖 正在启动 AI 安装助手...');")
            self.execute_js(f"startMCPInstallAnalysis('{item_id}', '{install_url}', '{repo_dir_name}', '{install_name}', '{abs_path}');")

        threading.Thread(target=worker, daemon=True).start()

    # ==========================================
    # AI 安装助手工具
    # ==========================================

    @pyqtSlot(str, result=str)
    def listServerFiles(self, server_id: str):
        """列出服务器目录下的文件列表（供 AI 工具调用），AI 根据列表决定要读取哪些文件
        支持子目录路径如 project_human/mcp-servers"""
        try:
            base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "mcp", "server")
            parts = server_id.replace('\\', '/').split('/')
            root_dir = parts[0]
            sub_path = '/'.join(parts[1:]) if len(parts) > 1 else ''
            
            for root in os.listdir(base):
                if root == root_dir or root.lower() == root_dir.lower():
                    path = os.path.join(base, root, sub_path) if sub_path else os.path.join(base, root)
                    if not os.path.isdir(path):
                        return f"⚠️ 路径 {server_id} 不是一个目录"
                    files = sorted(os.listdir(path))
                    details = []
                    for f in files:
                        fpath = os.path.join(path, f)
                        if os.path.isdir(fpath):
                            details.append(f"📁 {f}/ (目录)")
                        else:
                            size = os.path.getsize(fpath)
                            details.append(f"📄 {f} ({size} bytes)")
                    return "📂 文件列表:\n" + "\n".join(details)
            return f"⚠️ 服务器目录 {server_id} 未找到"
        except Exception as e:
            return f"❌ 列表失败: {str(e)}"

    @pyqtSlot(str, result=str)
    def readServerFile(self, server_id: str, filename: str):
        """读取服务器文件内容（供 AI 工具调用），自动跳过目录
        支持子目录路径如 project_human/mcp-servers 和子目录文件如 mcp-servers/package.json"""
        try:
            base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "mcp", "server")
            # 支持子目录路径
            parts = server_id.replace('\\', '/').split('/')
            root_dir = parts[0]
            sub_path = '/'.join(parts[1:]) if len(parts) > 1 else ''
            
            # filename 可能也包含子路径如 "mcp-servers/package.json"
            file_parts = filename.replace('\\', '/').split('/')
            
            for root in os.listdir(base):
                if root == root_dir or root.lower() == root_dir.lower():
                    # 构建完整路径: base/root/sub_path/file_parts...
                    full_path = os.path.join(base, root, sub_path, *file_parts) if sub_path else os.path.join(base, root, *file_parts)
                    
                    if os.path.exists(full_path):
                        if os.path.isdir(full_path):
                            return f"⚠️ {filename} 是一个目录，跳过读取。请指定具体的文件名。"
                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                content = f.read(5000)
                            return f"📄 {filename} ({len(content)} 字符):\n{content}"
                        except UnicodeDecodeError:
                            return f"⚠️ 文件 {filename} 是二进制文件，无法读取"
                    else:
                        # 尝试列出目录内容帮助排查
                        parent_dir = os.path.join(base, root, sub_path) if sub_path else os.path.join(base, root)
                        if os.path.isdir(parent_dir):
                            dir_files = os.listdir(parent_dir)
                            return f"⚠️ 文件 {filename} 不存在。可读取: {', '.join(dir_files[:30])}"
                        return f"⚠️ 目录 {server_id} 不存在"
            return f"⚠️ 服务器目录 {server_id} 未找到"
        except Exception as e:
            return f"❌ 读取失败: {str(e)}"

    @pyqtSlot(str)
    def openExternalUrl(self, url: str):
        """在系统默认浏览器中打开 URL（解决 QWebEngineView 无法打开 `target=_blank` 链接的问题）"""
        import webbrowser
        try:
            webbrowser.open(url)
            print(f"[MCPBridge] 🌐 在系统浏览器中打开: {url}")
        except Exception as e:
            print(f"[MCPBridge] ❌ 打开 URL 失败: {e}")

    @pyqtSlot(result=str)
    def getLocalServerDirs(self):
        """返回 tools/mcp/server/ 下所有已下载的 MCP 项目目录列表"""
        try:
            base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "mcp", "server")
            if not os.path.exists(base):
                return "[]"
            result = []
            for name in sorted(os.listdir(base)):
                path = os.path.join(base, name)
                if os.path.isdir(path) and not name.startswith('.'):
                    result.append({
                        "name": name,
                        "path": name,
                        "hasPackageJson": os.path.exists(os.path.join(path, "package.json")),
                        "hasMcpJson": os.path.exists(os.path.join(path, ".mcp.json")),
                        "hasPyproject": os.path.exists(os.path.join(path, "pyproject.toml")),
                    })
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            print(f"[MCPBridge] ❌ getLocalServerDirs 失败: {e}")
            return "[]"

    @pyqtSlot(str, result=str)
    def detectLocalServer(self, dir_name: str):
        """检测本地 MCP 项目目录，返回名称、入口、类型等信息"""
        try:
            base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "mcp", "server")
            path = os.path.join(base, dir_name)
            if not os.path.isdir(path):
                return json.dumps({"error": f"目录不存在: {dir_name}"})
            
            info = {
                "name": dir_name,
                "description": "",
                "entryPoint": "",
                "command": "node",
                "args": [],
                "cwd": path,
                "isHttp": False,
                "httpUrl": "",
                "packageManager": "npm",
            }
            
            # 检测 .mcp.json（HTTP 远程）
            mcp_json = _read_json_file(os.path.join(path, ".mcp.json"))
            for srv_name, srv_cfg in mcp_json.get("mcpServers", {}).items():
                if srv_cfg.get("type") == "http" and srv_cfg.get("url"):
                    info["isHttp"] = True
                    info["httpUrl"] = srv_cfg["url"]
                    info["name"] = srv_name
                    break
            
            # 检测 package.json
            pkg = _read_json_file(os.path.join(path, "package.json"))
            if pkg:
                info["hasPackageJson"] = True
                info["name"] = pkg.get("name", info["name"])
                info["description"] = pkg.get("description", info["description"])
                
                # 检测入口
                bin_field = pkg.get("bin", {})
                if isinstance(bin_field, dict) and bin_field:
                    bin_name, bin_script = next(iter(bin_field.items()))
                    bin_path = os.path.join(path, bin_script)
                    if os.path.exists(bin_path):
                        info["command"] = "node"
                        info["args"] = [bin_script]
                        info["entryPoint"] = bin_script
                elif isinstance(bin_field, str):
                    bin_path = os.path.join(path, bin_field)
                    if os.path.exists(bin_path):
                        info["command"] = "node"
                        info["args"] = [bin_field]
                        info["entryPoint"] = bin_field
                
                if not info["entryPoint"]:
                    main_field = pkg.get("main", "")
                    if main_field:
                        main_path = os.path.join(path, main_field)
                        if os.path.exists(main_path):
                            info["command"] = "node"
                            info["args"] = [main_field]
                            info["entryPoint"] = main_field
                
                # 包管理器
                if os.path.exists(os.path.join(path, "pnpm-workspace.yaml")) or os.path.exists(os.path.join(path, "pnpm-lock.yaml")):
                    info["packageManager"] = "pnpm"
                elif os.path.exists(os.path.join(path, "yarn.lock")):
                    info["packageManager"] = "yarn"
            
            # 检测 pyproject.toml
            if os.path.exists(os.path.join(path, "pyproject.toml")):
                info["hasPyproject"] = True
                if not info["entryPoint"]:
                    info["command"] = "python"
                    info["args"] = ["-m", "mcp_server"]
            
            return json.dumps(info, ensure_ascii=False)
        except Exception as e:
            print(f"[MCPBridge] ❌ detectLocalServer 失败: {e}")
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, str)
    def confirmEnvVars(self, server_id: str, env_json: str):
        """接收前端 API Key 对话框的确认，保存环境变量到安装上下文
        两种情况：
        1. AI 还未调用 finalizeMCPInstall → 保存到 _install_context 等待后续写入
        2. AI 已经调用 finalizeMCPInstall（配置已写入文件但 env 为空）→ 直接更新配置文件并重启
        """
        print(f"[MCPBridge] 📥 confirmEnvVars 被调用: server_id={server_id}")
        print(f"[MCPBridge] 📥 env_json 原始内容: {env_json[:200]}")
        try:
            env_vars = json.loads(env_json)
            
            # === 情况1：安装上下文还在，保存等后续 finalize ==
            ctx = getattr(self, '_install_context', None)
            if ctx:
                ctx["env_vars"] = env_vars
                self._install_context = ctx
            
            # === 情况2：配置已写入文件但 env 可能为空，直接更新配置文件 ===
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = mgr._read_config()
            servers = config.get("mcpServers", {})
            if server_id in servers:
                old_env = servers[server_id].get("env", {})
                # 仅当 env 有变化时才写文件
                if old_env != env_vars:
                    servers[server_id]["env"] = {**old_env, **env_vars}  # 用户值覆盖旧值
                    mgr._write_config(config)
                    print(f"[MCPBridge] ✅ 已更新配置文件中的环境变量")
                    self.execute_js(f"mcpAppendLog('{server_id}', '✅ 已更新配置文件中的环境变量');")
                    self.execute_js(f"mcpAppendLog('{server_id}', '✅ Key 已配置完成，AI 将继续完成安装');")
            else:
                print(f"[MCPBridge] ⚠️ 配置文件不存在 server_id={server_id}，仅保存到安装上下文")
            
            masked_keys = ", ".join([f"{k}=****" for k in env_vars.keys()])
            print(f"[MCPBridge] ✅ 已保存环境变量: {masked_keys}")
            # 通知 AI 环境变量已填写完成（不带 key 值，仅告知状态）
            self.execute_js(f"window.chatApp && window.chatApp.addMessage && window.chatApp.addMessage('user', '用户已确认环境变量，AI 可以继续下一步');")
            print(f"[MCPBridge] ✅ 已通知 AI 继续安装")
        except Exception as e:
            print(f"[MCPBridge] ❌ confirmEnvVars 失败: {e}")
            import traceback
            traceback.print_exc()

    @pyqtSlot(str, str, str)
    def finalizeMCPInstall(self, item_id: str, config_json: str, extra_info: str):
        """完成安装（供 AI 工具调用）
        
        AI 分析完所有文件后，提供完整的 MCP 服务器配置 JSON。
        后端只做：合并环境变量 → 写入配置文件 → 启动服务。
        不再自动检测任何内容，所有检测逻辑由 AI 完成。
        """
        try:
            if extra_info:
                self.execute_js(f"mcpAppendLog('{item_id}', '📝 {extra_info[:200]}');")
            ctx = getattr(self, '_install_context', None)
            if not ctx:
                self.execute_js(f"mcpAppendLog('{item_id}', '❌ 安装上下文丢失');")
                self.execute_js(f"mcpFinishInstall('{item_id}', -1);")
                return
            # AI 传入的 item_id 可能是 config_id（目录名），不是市场 ID
            # 从上下文获取原始市场 item_id
            market_item_id = ctx.get("item_id", item_id)
            cfg = json.loads(config_json)  # AI 提供的完整配置

            # 合并用户确认的环境变量（用户输入始终覆盖 AI 传的值）
            if ctx.get("env_vars"):
                user_env = ctx["env_vars"]
                ai_env = cfg.get("env", {})
                cfg["env"] = {**ai_env, **user_env}  # user_env 覆盖 ai_env 中同名的空值

            write_id = ctx["config_id"]
            clone_dir = ctx["clone_dir"]

            # 构建最终配置（以 AI 提供为准，后端仅补充 githubRepoUrl）
            server_config = {
                "transport": cfg.get("transport", "stdio"),
                "enabled": True,
                "auto_start": True,
                "description": cfg.get("description", ctx.get("name", "")),
                "name": cfg.get("name", ctx.get("name", "")),
                "githubRepoUrl": ctx.get("repo_url", ""),
                "env": cfg.get("env", {}),
            }

            # HTTP 远程
            if server_config["transport"] == "http":
                server_config["url"] = cfg.get("url", "")
                self.execute_js(f"mcpAppendLog('{item_id}', '🌐 HTTP 远程服务器: {cfg.get("url", "")}');")
            # STDIO 本地 — cwd 统一转为绝对路径
            else:
                server_config["command"] = cfg.get("command", "python")
                server_config["args"] = cfg.get("args", ["-m", "mcp_server"])
                raw_cwd = cfg.get("cwd", clone_dir)
                if raw_cwd and not os.path.isabs(raw_cwd):
                    raw_cwd = os.path.abspath(raw_cwd)
                server_config["cwd"] = raw_cwd

            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            config = mgr._read_config()
            servers = config.setdefault("mcpServers", {})
            servers[write_id] = server_config
            mgr._write_config(config)
            self.execute_js(f"mcpAppendLog('{item_id}', '✅ 配置已写入 mcp_servers.json');")

            if server_config.get("enabled", True):
                self.execute_js(f"mcpAppendLog('{item_id}', '📡 正在启动 MCP 服务...');")
                # 在后台线程启动服务器，避免阻塞 AI 异步事件循环
                import threading as _th
                def _start_server():
                    try:
                        success = mgr.register_client(write_id, server_config)
                        if success:
                            host = mgr._clients.get(write_id)
                            if host:
                                tools = host.list_tools()
                                tool_names = [t.name for t in tools]
                                self.execute_js(f"mcpAppendLog('{item_id}', '✅ 服务器已启动！🔧 {" ".join(tool_names)}');")
                                self._register_mcp_tools_to_ai(write_id, mgr)
                            else:
                                self.execute_js(f"mcpAppendLog('{item_id}', '✅ 服务器已注册到配置');")
                        else:
                            self.execute_js(f"mcpAppendLog('{item_id}', '⚠️ 服务启动失败');")
                    except Exception as e:
                        self.execute_js(f"mcpAppendLog('{item_id}', '❌ 启动异常: {str(e)[:100]}');")
                    self.execute_js(f"mcpAppendLog('{item_id}', '════════════ 安装完成 ════════════════');")
                    # 用市场 ID 通知前端更新安装按钮
                    self.execute_js(f"mcpFinishInstall('{market_item_id}', 0);")
                    self.execute_js("loadMCPServers();")
                _th.Thread(target=_start_server, daemon=True).start()
            else:
                self.execute_js(f"mcpAppendLog('{item_id}', '════════════ 安装完成 ════════════════');")
                # 用市场 ID 通知前端更新安装按钮
                self.execute_js(f"mcpFinishInstall('{market_item_id}', 0);")
                self.execute_js("loadMCPServers();")
            # 持久化 installed 状态到数据库
            try:
                from storage.repositories.mcp_market_repo import MCPMarketRepository
                repo = MCPMarketRepository()
                db_item = repo.get_by_id(ctx.get("item_id", "")) if hasattr(repo, 'get_by_id') else {}
                if db_item:
                    db_item["installed"] = True
                    repo.upsert(db_item)
            except Exception:
                pass
            return  # 后续由后台线程完成，避免重复执行 finish
        except Exception as e:
            self.execute_js(f"mcpAppendLog('{item_id}', '❌ 安装失败: {str(e)[:100]}');")
            self.execute_js(f"mcpFinishInstall('{item_id}', -1);")

    @pyqtSlot(str, str)
    def uninstallMCPFromMarket(self, item_id: str, cmd: str):
        import threading, shutil
        def worker():
            self._write_log(item_id, "🔄 正在卸载...")
            self.execute_js(f"mcpAppendLog('{item_id}', '══════════════════ 卸载日志 ══════════════════');")
            self.execute_js(f"mcpAppendLog('{item_id}', '🗑️ 正在卸载 MCP 服务器: {item_id}');")
            self.execute_js(f"mcpAppendLog('{item_id}', '── ① 停止服务 ──');")
            try:
                from tools.mcp.host import MCPHost; mgr = MCPHost()
                mgr.unregister_client(item_id)
                self.execute_js(f"mcpAppendLog('{item_id}', '🛑 服务已停止');")
            except Exception as e:
                self.execute_js(f"mcpAppendLog('{item_id}', '⚠️ 停止服务失败: {str(e)[:50]}');")
            self.execute_js(f"mcpAppendLog('{item_id}', '── ② 删除配置 ──');")
            try:
                from tools.mcp.host import MCPHost; mgr = MCPHost()
                mgr.remove_remote_server(item_id)
                self.execute_js(f"mcpAppendLog('{item_id}', '✅ 配置已删除');")
            except Exception as e:
                self.execute_js(f"mcpAppendLog('{item_id}', '⚠️ 删除配置失败: {str(e)[:50]}');")
            self.execute_js(f"mcpAppendLog('{item_id}', '── ③ 删除项目目录 ──');")
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_dir = os.path.join(base, "tools", "mcp", "server", item_id)
            try:
                from tools.mcp.host import MCPHost; mgr = MCPHost()
                cfg = mgr._read_config().get("mcpServers", {}).get(item_id, {})
                saved = cfg.get("githubRepoUrl", "")
                if saved:
                    config_dir = os.path.join(base, "tools", "mcp", "server", saved.rstrip('/').split('/')[-1].replace('.git','').lower())
            except Exception: pass
            if os.path.exists(config_dir):
                shutil.rmtree(config_dir)
            self.execute_js(f"mcpAppendLog('{item_id}', '✅ 卸载完成！');")
            self.execute_js(f"mcpFinishInstall('{item_id}', 0);")
            self.execute_js("loadMCPServers();")
            # 持久化 installed 状态到数据库
            try:
                from storage.repositories.mcp_market_repo import MCPMarketRepository
                repo = MCPMarketRepository()
                db_item = repo.get_by_id(item_id)
                if db_item:
                    db_item["installed"] = False
                    repo.upsert(db_item)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def register_tools_to_dispatcher(self, mcp_dispatcher):
        try:
            from tools.mcp.host import MCPHost; mgr = MCPHost()
        except Exception as e:
            print(f"[MCPBridge] ❌ register_tools_to_dispatcher 失败: {e}")