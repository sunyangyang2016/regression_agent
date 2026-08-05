"""
MCP 主机 — 统一管理 MCP 客户端
职责：客户端生命周期 + 工具汇总 + 工具路由
支持：
- stdio 子进程（本地安装）
- HTTP 远程服务  
- JSON 配置读写
"""
import concurrent.futures
import os
import json
import subprocess
import time
import threading
from typing import Optional, Callable, Dict, List, Any
from tools.mcp.local_client import MCPLocalClient
from tools.mcp.http_client import MCPHTTPClient
from config.user_config import USER_DIR, resolve_config_path


LOG = "[MCP-Host]"


class MCPHost:
    """MCP 主机 — 统一管理所有 MCP 客户端
    
    核心职责：
    1. 客户端生命周期 — 启动/停止/注册 MCP 子进程
    2. 工具汇总 — 收集所有 Client 的工具定义
    3. 工具路由 — 根据工具名找到对应的 Client 并执行
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_dir: str = None, on_ready: Callable = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # 用户配置写入目录：user_config/user/（默认配置在 defaults/ 下，只读不修改）
        self.config_dir = config_dir or USER_DIR
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 已启动的 Client 列表
        self._clients: Dict[str, MCPLocalClient] = {}
        self._tool_handlers: Dict[str, Callable] = {}
        self._on_ready = on_ready
        self._initialized = True
        self._loading = True  # 标记正在后台加载中
        
        # 后台线程加载服务器，不阻塞 __init__
        def _bg_load():
            try:
                self._load_servers_from_config()
            finally:
                self._loading = False
                if self._on_ready:
                    try:
                        self._on_ready(self)
                    except Exception:
                        pass
        
        t = threading.Thread(target=_bg_load, daemon=True)
        t.start()
    
    # ==========================================
    # 配置文件管理
    # ==========================================
    
    def _get_config_path(self) -> str:
        """读取配置路径：优先 user/ 目录，回退 defaults/ 目录"""
        return resolve_config_path("mcp_servers.json")
    
    def _read_config(self) -> Dict:
        path = self._get_config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"{LOG} ⚠️ 读取配置失败: {e}")
        return {"mcpServers": {}}
    
    def _write_config(self, config: Dict):
        """写入配置到 user/ 目录（defaults 目录保持初始化状态，永远不被修改）

        - 首次写入时：若 user/ 无文件且 defaults/ 有初始化配置，先合并初始化 + 新配置再落盘
          这样 user/ 成为完整快照（初始化 + 新安装），此后显示直接走 user/。
        - 始终使用 save_config（强制写 user_config/user/），不依赖 self.config_dir。
        """
        from config.user_config import save_config
        # 首次写入：合并 defaults/ 的初始化配置，确保 user/ 快照完整
        from config.user_config import DEFAULTS_DIR
        user_mc = os.path.join(USER_DIR, "mcp_servers.json")
        if not os.path.exists(user_mc):
            defaults_path = os.path.join(DEFAULTS_DIR, "mcp_servers.json")
            if os.path.exists(defaults_path):
                try:
                    with open(defaults_path, "r", encoding="utf-8") as f:
                        defaults_cfg = json.load(f)
                    merged_servers = dict(defaults_cfg.get("mcpServers", {}))
                    merged_servers.update(config.get("mcpServers", {}))
                    config = {"mcpServers": merged_servers}
                except Exception:
                    pass
        save_config("mcp_servers.json", config)
    
    _status_change_callbacks: List[Callable] = []
    
    @classmethod
    def on_status_change(cls, cb: Callable):
        if cb not in cls._status_change_callbacks:
            cls._status_change_callbacks.append(cb)
    
    @classmethod
    def _fire_status_change(cls):
        for cb in cls._status_change_callbacks:
            try:
                cb()
            except Exception:
                pass
    
    # 并行加载的最大并发数（可用环境变量 AGENT_MCP_PARALLEL 覆盖）
    _MAX_PARALLEL_LOAD = max(1, int(os.environ.get("AGENT_MCP_PARALLEL", "4")))

    def _load_servers_from_config(self):
        """从配置文件加载所有启用的 MCP 客户端（并行启动，缩短加载等待）"""
        config = self._read_config()
        servers = config.get("mcpServers", {})
        enabled = [(sid, cfg) for sid, cfg in servers.items() if cfg.get("enabled", True)]
        if not enabled:
            # 保持原行为：配置里存在服务器时仍触发一次状态刷新（完善前端总数）
            if servers:
                self._fire_status_change()
            return

        max_workers = max(1, min(self._MAX_PARALLEL_LOAD, len(enabled)))

        def _load_one(item):
            sid, cfg = item
            try:
                ok = self.register_client(sid, cfg)
            except Exception as e:
                import traceback
                print(f"{LOG} ❌ [{sid}] 启动异常: {e}")
                traceback.print_exc()
                ok = False
            if ok:
                self._fire_status_change()  # 每启动成功一个就更新前端显示 X/N
            return ok

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="mcp-loader"
        ) as executor:
            results = list(executor.map(_load_one, enabled))

        success = sum(1 for ok in results if ok)
        # 全部加载完成后触发最终 UI 刷新（完善总数）
        self._fire_status_change()
        print(f"{LOG} ✅ 后台加载完成：{success}/{len(enabled)} 个服务器已启动")
    
    # ==========================================
    # 客户端生命周期
    # ==========================================
    
    def register_client(self, server_id: str, config: dict = None) -> bool:
        """注册并启动一个 MCP 客户端"""
        # 每次调用先重置上次错误，避免透传旧错误
        self.last_error = ""
        if config is None:
            config = self._read_config().get("mcpServers", {}).get(server_id)
            if config is None:
                print(f"{LOG} ❌ [{server_id}] 配置不存在")
                self.last_error = "配置不存在"
                return False
        
        transport = config.get("transport", "")
        if not transport:
            # 自动推断：有 url 则 HTTP，否则 stdio
            if "url" in config and config["url"]:
                transport = "http"
            else:
                transport = "stdio"
        
        if transport == "http":
            url = config.get("url", "")
            print(f"{LOG} ✅ [{server_id}] 远程服务: {url}")
            env = config.get("env", {})
            
            # 创建认证回调：当 HTTP 服务器返回 401 时弹出 API Key 输入框
            def on_auth_required(prompt_message):
                print(f"{LOG} 🔑 [{server_id}] 需要 API Key 认证")
                try:
                    from bridge.mcp_bridge import MCPBridge
                    bridge = MCPBridge._instance if hasattr(MCPBridge, '_instance') else None
                    if bridge:
                        env_vars = [{
                            "name": "API_KEY",
                            "description": prompt_message,
                            "required": True,
                            "url": url
                        }]
                        bridge.execute_js(f"showAPIKeyDialog({{server_id:'{server_id}',env_vars:{json.dumps(env_vars, ensure_ascii=False)}}});")
                        print(f"{LOG} ✅ [{server_id}] 已弹出 API Key 输入框")
                        return True
                except Exception as e:
                    print(f"{LOG} ⚠️ [{server_id}] 弹出认证框失败: {e}")
                return False
            
            client = MCPHTTPClient(server_id, url, env, on_auth_required)
            if client.start():
                self._clients[server_id] = client
                print(f"{LOG} ✅ [{server_id}] HTTP 连接成功 ({len(client.list_tools())} 个工具)")
                return True
            # 透传具体错误原因到上层
            if getattr(client, 'last_error', ''):
                self.last_error = client.last_error
            print(f"{LOG} ❌ [{server_id}] HTTP 连接失败: {self.last_error}")
            return False
        
        elif transport == "stdio":
            command = config.get("command", "")
            args = config.get("args", [])
            if isinstance(command, str):
                cmd = [command] + args
            else:
                cmd = command + args
            
            # 系统命令白名单 — 这些命令不进行路径解析
            SYSTEM_COMMANDS = {"node", "npx", "npm", "yarn", "pnpm", "uv", "python", "python3", "pip", "pip3"}
            
            # 将相对路径参数转为绝对路径（基于 cwd）
            cwd = config.get("cwd", self.config_dir)
            if cwd and cmd[0] not in SYSTEM_COMMANDS:
                resolved_cmd = []
                for part in cmd:
                    # 如果参数是相对路径且文件存在，转为绝对路径
                    if part == os.path.basename(part) and os.path.isfile(os.path.join(cwd, part)):
                        resolved_cmd.append(os.path.join(cwd, part))
                    elif part == cwd:
                        resolved_cmd.append(part)
                    else:
                        # 检查是否是相对路径脚本
                        candidate = os.path.join(cwd, part)
                        if os.path.isfile(candidate):
                            resolved_cmd.append(candidate)
                        else:
                            resolved_cmd.append(part)
                cmd = resolved_cmd
            print(f"{LOG} 📋 [{server_id}] 解析后命令: {cmd}")
            
            env = config.get("env", {})
            
            client = MCPLocalClient(server_id, cmd, env, cwd)
            if client.start_sync():
                self._clients[server_id] = client
                print(f"{LOG} ✅ [{server_id}] 已启动 ({len(client.list_tools())} 个工具)")
                return True
            return False
        
        else:
            print(f"{LOG} ⚠️ [{server_id}] 未知传输类型: {transport}")
            return False
    
    def unregister_client(self, server_id: str) -> bool:
        """停止并注销一个 MCP 客户端"""
        client = self._clients.pop(server_id, None)
        if client:
            client.cleanup_sync()
            print(f"{LOG} 🛑 [{server_id}] 已停止")
        return True

    # ==========================================
    # 工具汇总（供 AI 调用）
    # ==========================================
    
    def get_tools(self) -> List[Dict]:
        """获取所有 MCP 工具定义（OpenAI 格式）
        
        遍历所有已连接的 MCPClient，合并它们的工具列表。
        这是 AI 模型看到的所有 MCP 工具合集。
        线程安全：后台加载线程可能并发向 _clients 插入新客户端，
        遍历前先做快照，避免字典在迭代时被修改。
        """
        tools = []
        # 后台加载线程可能正并发修改 _clients，先快照再遍历
        for sid, client in list(self._clients.items()):
            client_tools = client.get_openai_tools()
            if client_tools:
                print(f"{LOG} 📋 [{sid}] 提供 {len(client_tools)} 个工具")
            tools.extend(client_tools)
        return tools
    
    def get_client_for_tool(self, tool_name: str):
        """根据工具名查找对应的 MCPClient
        
        路由功能：遍历所有 Client，找到提供该工具的 Client。
        
        Returns:
            (MCPClient, MCPTool) 或 (None, None)
        """
        for client in self._clients.values():
            for t in client.list_tools():
                if t.name == tool_name:
                    return client, t
        return None, None

    # ==========================================
    # 工具执行（路由到正确的 Client）
    # ==========================================
    
    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """执行 MCP 工具
        
        路由流程：
        1. 先查 tool_handlers 中的注册处理器
        2. 找到对应的 Client 并通过 JSON-RPC 调用
        3. 未找到则返回错误
        
        Args:
            tool_name: 工具名称（如 scrape_url）
            arguments: 参数字典
            
        Returns:
            工具执行结果字符串
        """
        handler = self._tool_handlers.get(tool_name)
        if handler:
            try:
                return handler(arguments)
            except Exception as e:
                return f"❌ 工具 '{tool_name}' 执行失败: {str(e)}"
        
        client, tool = self.get_client_for_tool(tool_name)
        if client and tool:
            print(f"{LOG} 🔀 路由 '{tool_name}' → {client.server_id}")
            try:
                return client.call_tool_sync(tool_name, arguments)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return f"❌ 工具 '{tool_name}' 调用失败: {str(e)}"
        
        return f"⚠️ 工具 '{tool_name}' 未安装，请先安装对应的 MCP 服务器"
    
    def register_tool_handler(self, name: str, handler: Callable):
        """注册工具处理器"""
        self._tool_handlers[name] = handler

    # ==========================================
    # 远程服务器管理（HTTP 模式）
    # ==========================================
    
    def add_remote_server(self, name: str, url: str, api_key: str = "") -> bool:
        """添加远程 MCP 服务器到配置文件"""
        config = self._read_config()
        servers = config.setdefault("mcpServers", {})
        server_cfg = {
            "transport": "http",
            "url": url,
            "enabled": True,
            "description": f"{name} 远程服务"
        }
        if api_key:
            server_cfg["env"] = {"API_KEY": api_key}
        servers[name] = server_cfg
        self._write_config(config)
        print(f"{LOG} ✅ 已添加远程服务器: {name} ({url})")
        return True
    
    def remove_remote_server(self, name: str) -> bool:
        config = self._read_config()
        servers = config.get("mcpServers", {})
        if name in servers:
            del servers[name]
            self._write_config(config)
            print(f"{LOG} 🗑️ 已删除: {name}")
            return True
        return False
    
    def get_all_servers(self) -> List[Dict]:
        """获取所有已配置的服务器列表（用于前端展示）"""
        config = self._read_config()
        servers = config.get("mcpServers", {})
        # 后台加载线程可能正并发修改 _clients，先做快照保证安全遍历
        clients = dict(self._clients)
        result = []
        for sid, cfg in servers.items():
            transport = cfg.get("transport", "")
            if not transport:
                # 智能判断：没有 transport 字段时根据配置内容推断
                if "url" in cfg and cfg["url"]:
                    transport = "http"
                else:
                    transport = "stdio"
            env = cfg.get("env", {}) or {}
            result.append({
                "id": sid,
                "name": cfg.get("name", sid),
                "url": cfg.get("url", ""),
                "description": cfg.get("description", ""),
                "transport": transport,
                "enabled": cfg.get("enabled", True),
                "online": bool(clients.get(sid)) and clients[sid].is_running(),
                "githubRepoUrl": cfg.get("githubRepoUrl", ""),
                "env": env,
            })
        return result

    # ==========================================
    # 生命周期
    # ==========================================
    
    def wait_ready(self, timeout: float = 0.0) -> bool:
        """等待后台加载完成（默认不等待）。

        Args:
            timeout: 最多等待秒数；<=0 表示不等待，立即返回当前状态。

        Returns:
            True 表示加载已完成；False 表示仍在加载（或等待超时）。
        """
        if not self._loading:
            return True
        if timeout <= 0:
            return False
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            if not self._loading:
                return True
            _time.sleep(0.1)
        return not self._loading
    
    def stop_all(self):
        for sid in list(self._clients.keys()):
            self.unregister_client(sid)
    
    def cleanup(self):
        self.stop_all()
        MCPHost._instance = None
        self._initialized = False
        print(f"{LOG} 🧹 已清理")