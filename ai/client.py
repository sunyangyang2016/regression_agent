"""
AI 客户端 - 异步封装
整合流式处理器、工具调度器、消息管理
"""
import asyncio
import concurrent.futures
import threading
from typing import Optional, Callable
from ai.protocol import Message, ModelConfig, AIStreamEvent, ToolCallInfo
from ai.stream_handler import StreamHandler
from ai.tool_dispatcher import ToolDispatcher
from ai.mcp_dispatcher import MCPDispatcher
from core.event_bus import EventBus


class AIClient:
    """异步 AI 客户端 - 封装与大模型的交互
    
    特性：
    - 完整的异步支持（asyncio）
    - 流式输出 + 实时事件
    - 多轮工具调用
    - Qt 主线程安全的事件分发
    """
    
    def __init__(self, model_config):
        self.model_config = model_config
        self._model_config: Optional[ModelConfig] = None
        self.stream_handler: Optional[StreamHandler] = None
        self._connected = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        # 底层 AI 通信原始 JSON 日志回调（由 AIController 注入）
        self.on_raw_log: Optional[Callable[[str], None]] = None
        self.on_progress_usage: Optional[Callable[[str], None]] = None
        
        # ========== 工具调度系统 ==========
        # 1. 内建工具调度器 — 处理本地工具（calculate, docker_ps 等）
        self.tool_dispatcher = ToolDispatcher()
        # 2. MCP 工具调度器 — 处理 MCP 协议工具（通过 MCPHost 子进程通信）
        self.mcp_dispatcher = MCPDispatcher()
        # 3. Skill 调度器 — 处理技能调用（由 AppController 在初始化时注入）
        self.skill_dispatcher = None
        
        # 事件总线
        self.bus = EventBus()
        
        # 对话消息
        self.messages: list = []
        self._system_prompt: str = ""

        # 当前运行中的 AI 流式任务（用于中断）
        self._current_task: Optional[concurrent.futures.Future] = None

        # 工具名映射：{API 规范化名称: 原始工具名}
        # 由 _get_tools_for_api 在每次发送前重建，供模型回调时还原真实工具名执行
        self._tool_name_map: dict = {}

    # ==========================================
    # 事件循环管理
    # ==========================================
    
    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        """获取或创建事件循环（线程安全）"""
        if self._event_loop is None or self._event_loop.is_closed():
            self._event_loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._event_loop.run_forever,
                daemon=True,
                name="ai-asyncio-loop"
            )
            self._loop_thread.start()
        return self._event_loop

    # ==========================================
    # 连接管理
    # ==========================================
    
    def connect(self) -> tuple:
        """连接 AI API"""
        try:
            self._model_config = ModelConfig.from_dict(self.model_config.config)
            
            if not self._model_config.api_key:
                return False, "请配置 API Key"
            
            # 创建流式处理器（传入内建 + MCP 两个调度器）
            self.stream_handler = StreamHandler(
                self._model_config,
                self.tool_dispatcher,
                self.mcp_dispatcher,
                name_resolver=self._resolve_tool_api_name
            )
            # 注入底层原始 JSON 日志回调
            if self.on_raw_log:
                self.stream_handler.on_raw_log = self.on_raw_log
            # 注入中间进度 token 回调
            if self.on_progress_usage:
                self.stream_handler.on_progress_usage = self.on_progress_usage
            client = self.stream_handler.create_client()
            
            if client is None:
                return False, "客户端创建失败"
            
            self._connected = True
            self._system_prompt = self.model_config.get("chat", "system_prompt")
            self.messages = [{"role": "system", "content": self._system_prompt}]
            
            self.bus.emit(EventBus.SYS_CONNECTED, True)
            return True, "已连接"
            
        except Exception as e:
            self._connected = False
            self.bus.emit(EventBus.AI_ERROR, str(e))
            return False, str(e)
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def reconnect(self):
        """热切换配置：不重启事件循环，只更换 ModelConfig 和 StreamHandler"""
        try:
            self._model_config = ModelConfig.from_dict(self.model_config.config)
            if not self._model_config.api_key:
                return False, "请配置 API Key"
            self.stream_handler = StreamHandler(
                self._model_config,
                self.tool_dispatcher,
                self.mcp_dispatcher,
                name_resolver=self._resolve_tool_api_name
            )
            # 注入底层原始 JSON 日志回调（热切换后重建 StreamHandler 需重新注入）
            if self.on_raw_log:
                self.stream_handler.on_raw_log = self.on_raw_log
            if self.on_progress_usage:
                self.stream_handler.on_progress_usage = self.on_progress_usage
            client = self.stream_handler.create_client()
            if client is None:
                return False, "客户端创建失败"
            self._connected = True
            self._system_prompt = self.model_config.get("chat", "system_prompt")
            self.messages = [{"role": "system", "content": self._system_prompt}]
            self.bus.emit(EventBus.SYS_CONNECTED, True)
            return True, "已连接"
        except Exception as e:
            self._connected = False
            self.bus.emit(EventBus.AI_ERROR, str(e))
            return False, str(e)

    def cleanup(self):
        """清理资源"""
        self._connected = False
        # 取消正在运行的 AI 任务
        self.cancel_current()
        if self._event_loop and not self._event_loop.is_closed():
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)
        self.tool_dispatcher.clear()
        self.mcp_dispatcher.clear()
        if self.skill_dispatcher:
            self.skill_dispatcher.clear()
        self.messages.clear()

    # ==========================================
    # System Prompt 管理
    # ==========================================
    
    def set_system_prompt(self, prompt: str):
        """更新 system prompt"""
        self._system_prompt = prompt
        if self.messages:
            self.messages[0] = {"role": "system", "content": prompt}
    
    def inject_tool_context(self, tool_descriptions: str):
        """注入工具上下文到 system prompt"""
        enhanced = self._system_prompt + "\n\n" + tool_descriptions
        self.set_system_prompt(enhanced)

    def get_initial_messages(self):
        """获取初始消息列表（仅 system prompt）"""
        system_prompt = self.model_config.get("chat", "system_prompt")
        return [{"role": "system", "content": system_prompt}]

    # ==========================================
    # 消息发送
    # ==========================================
    
    def send_message(self, messages, content, on_chunk=None, on_complete=None,
                     on_error=None, on_tool_call=None, on_round=None):
        """发送消息 - 将 ChatManager 的 messages 同步到 AIClient 后调用"""
        self.messages = messages
        
        def _on_chunk(data):
            if on_chunk: on_chunk(data)
        
        def _on_complete(data):
            if on_complete: on_complete(data)
        
        def _on_error(err):
            if on_error: on_error(err)
        
        def _on_round(data):
            if on_round: on_round(data)
        
        def _on_tool_call(info):
            # tool_call 事件触发时 result 为空，先不显示，等 tool_result 再一起显示
            pass
        
        def _on_tool_result(info):
            # tool_result 事件触发时 result 有值，传递完整信息
            if on_tool_call:
                on_tool_call(info.name, info.arguments, info.result or "")
        
        self.send_message_async(
            content=content,
            on_chunk=_on_chunk,
            on_complete=_on_complete,
            on_error=_on_error,
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            on_round=_on_round
        )
    
    def send_message_async(self, content: str,
                           on_chunk: Optional[Callable[[str], None]] = None,
                           on_tool_call: Optional[Callable[[ToolCallInfo], None]] = None,
                           on_tool_result: Optional[Callable[[ToolCallInfo], None]] = None,
                           on_round: Optional[Callable[[dict], None]] = None,
                           on_complete: Optional[Callable[[str], None]] = None,
                           on_error: Optional[Callable[[str], None]] = None):
        """异步发送消息（启动后台任务）"""
        if not self._connected:
            if on_error:
                on_error("客户端未连接")
            return
        
        # 1. 添加用户消息
        self.messages.append({"role": "user", "content": content})
        
        # 2. 获取所有可用工具定义（内建 + MCP）
        tools = self._get_tools_for_api()
        
        # 3. 注入 MCP 服务器状态到 context
        self._inject_mcp_server_context()
        
        # 3.1 将已启用工具清单注入 system prompt
        # 解决：用户询问「安装了哪些工具」时，AI 因上下文中无工具清单文本，
        # 转而调用 directory_ops / execute_system_command 去翻查目录。
        # 注入后 AI 可直接据此回答，不再绕行调用文件/目录操作工具。
        self._inject_tool_context_into_system(tools)
        
        # 3.2 读取模型最大上下文容量（用于滑动窗口）
        try:
            max_context = self.model_config.get("api", "max_context") or 65536
        except Exception:
            max_context = 65536
        
        # 4. 启动流式对话
        loop = self._get_or_create_loop()
        
        async def run_chat():
            try:
                async for event in self.stream_handler.stream_chat(
                    messages=self.messages,
                    tools=tools,
                    max_rounds=30,
                    max_context=max_context
                ):
                    if event.type == "chunk":
                        if on_chunk:
                            on_chunk(event.data)
                        self.bus.emit(EventBus.AI_CHUNK_RECEIVED, event.data)
                    
                    elif event.type == "tool_call":
                        if on_tool_call:
                            on_tool_call(event.data)
                        self.bus.emit(EventBus.AI_TOOL_CALL, event.data)
                    
                    elif event.type == "tool_result":
                        if on_tool_result:
                            on_tool_result(event.data)
                        self.bus.emit(EventBus.AI_TOOL_RESULT, event.data)

                    elif event.type == "round":
                        if on_round:
                            on_round(event.data)
                        self.bus.emit(EventBus.AI_ROUND_RECEIVED, event.data)

                    elif event.type == "complete":
                        if on_complete:
                            on_complete(event.data)
                        self.bus.emit(EventBus.AI_RESPONSE_COMPLETE, event.data)
                    
                    elif event.type == "error":
                        if on_error:
                            on_error(event.error)
                        self.bus.emit(EventBus.AI_ERROR, event.error)
                    
                    elif event.type == "cancelled":
                        # 被用户中断：静默退出（不触发 complete/error）
                        return
                        
            except asyncio.CancelledError:
                # 任务被取消（用户中断）：静默退出，不触发错误回调
                pass
            except Exception as e:
                if on_error:
                    on_error(str(e))
        
        # 保存 task 引用（concurrent.futures.Future），便于中断
        self._current_task = asyncio.run_coroutine_threadsafe(run_chat(), loop)

    def cancel_current(self):
        """取消当前正在运行的 AI 流式任务（用户中断）"""
        if self._current_task is not None:
            try:
                self._current_task.cancel()
                print("[AI] ⏹ 已请求取消当前 AI 流式任务")
            except Exception as e:
                print(f"[AI] ⚠️ 取消 AI 任务失败: {e}")
            finally:
                self._current_task = None

    # ==========================================
    # 工具工具注册（内建 + MCP）
    # ==========================================
    
    def register_tool_handler(self, name: str, handler):
        """
        注册内建工具处理器
        由 BuiltinManager 在加载工具时调用
        """
        self.tool_dispatcher.register_sync(name, handler)

    def register_mcp_handler(self):
        """
        注册所有 MCP Host 的工具到 MCPDispatcher
        由 MCPBridge 在安装/启动 MCP 服务器后调用
        确保 AI 能通过 MCPDispatcher 路由到 MCPHost 执行
        """
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            registered = 0
            for host in mgr._clients.values():
                for t in host.list_tools():
                    tool_name = t.name
                    host_ref = host
                    
                    async def make_handler(args, tn=tool_name, cl=host_ref):
                        args = args or {}
                        return cl.call_tool(tn, args)
                    
                    self.mcp_dispatcher.register(tool_name, make_handler)
                    registered += 1
                    
            if registered > 0:
                print(f"[AI] 🔌 已注册 {registered} 个 MCP 工具到 MCPDispatcher")
        except Exception as e:
            print(f"[AI] ⚠️ 注册 MCP 工具失败: {e}")

    # ==========================================
    # 工具收集（发送给 AI 模型）
    # ==========================================
    
    def _get_tools_for_api(self) -> list:
        """
        获取所有注册工具的 OpenAI API 格式
        返回的列表将作为 tools 参数传递给 AI 模型
        """
        tools = []
        
        # 1. 内建工具（仅已启用的）
        tools.extend(self._get_builtin_tools())
        
        # 2. MCP Host 工具（通过子进程通信）
        tools.extend(self._get_mcp_tools())
        
        # 3. Skill 工具（通过 SkillDispatcher 注册）
        tools.extend(self._get_skill_tools())

        # 规范化为 OpenAI 兼容的合法函数名，并建立「API 名 → 原始名」映射
        # （MCP/技能名称可能含点号、空格、中文等非法字符，直接透传会 400）
        from ai.tool_names import sanitize_tools_for_api
        tools, self._tool_name_map = sanitize_tools_for_api(tools)

        if tools:
            print(f"[AI] 🚀 共 {len(tools)} 个工具传递给 AI 模型")
            renamed = sum(1 for t in tools if t.get("function", {}).get("name") in self._tool_name_map)
            if renamed:
                print(f"[AI] 🔧 已将 {renamed} 个工具名规范化为 OpenAI 兼容格式")
        else:
            print(f"[AI] ⚠️ 没有可用工具传递给 AI 模型")
        return tools
    
    def _resolve_tool_api_name(self, api_name: str) -> str:
        """将模型返回的 API 工具名还原为原始工具名（用于内部路由执行）"""
        from ai.tool_names import resolve_original_name
        return resolve_original_name(self._tool_name_map, api_name)

    def _inject_tool_context_into_system(self, tools: list) -> None:
        """将已启用工具清单注入到 system prompt（幂等：已注入则替换）

        背景：
        - tools 参数对模型来说只是「可调用的函数注册表」，不是「已安装软件清单」。
        - system prompt 若无工具清单文本，AI 被问「安装了哪些工具」时，
          会认为需要实际查看系统，转而调用 directory_ops / execute_system_command
          去翻查目录。
        - 注入明确标注的清单后，AI 可直接据此回答。

        幂等性：以「## 当前已安装的工具清单」为标记，已注入时先移除旧块再注入新块，
        保证启用状态变化后清单始终是最新的。
        """
        if not tools:
            return

        lines = ["\n## 当前已安装的工具清单"]
        lines.append("当用户询问安装了哪些工具、有哪些可用能力时，直接根据以下列表回答，不要调用任何工具去查看。")
        for t in tools:
            fn = t.get("function") or {}
            name = fn.get("name", "")
            desc = (fn.get("description") or "").strip().replace("\n", " ")
            if name:
                lines.append(f"- `{name}`: {desc[:120]}")
        tool_block = "\n".join(lines)

        marker = "## 当前已安装的工具清单"
        for i, msg in enumerate(self.messages):
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if marker in content:
                    # 替换旧块，保持最新启用状态
                    content = content.split(marker)[0].rstrip()
                content = (content + "\n" + tool_block).strip()
                self.messages[i] = {"role": "system", "content": content}
                break


    def _get_builtin_tools(self) -> list:
        """获取已启用的内建工具"""
        tools = []
        try:
            from tools.builtin.builtin_tools_manager import BuiltinManager
            bt = BuiltinManager().get_tools_for_api()
            if bt:
                print(f"[AI] 📦 加载 {len(bt)} 个已启用的内建工具:")
                for t in bt:
                    fn = t.get("function", {})
                    print(f"       - {fn.get('name')}: {fn.get('description')[:60]}")
            tools.extend(bt)
        except Exception as e:
            print(f"[AI] ❌ 获取内建工具失败: {e}")
        return tools
    
    def _get_skill_tools(self) -> list:
        """获取通过 SkillDispatcher 注册的 skill 工具"""
        tools = []
        if self.skill_dispatcher:
            try:
                st = self.skill_dispatcher.get_tool_descriptions()
                if st:
                    print(f"[AI] 🎯 加载 {len(st)} 个 skill 工具:")
                    for t in st:
                        fn = t.get("function", {})
                        print(f"       - {fn.get('name')}: {fn.get('description')[:60]}")
                tools.extend(st)
            except Exception as e:
                print(f"[AI] ❌ 获取 skill 工具失败: {e}")
        return tools

    def _get_mcp_tools(self) -> list:
        """获取 MCP Host 提供的工具

        不阻塞等待 MCP 后台加载：直接返回当前已加载的工具快照。
        后台加载完成后，工具会由 register_mcp_handler / _start_mcp_servers
        动态注册到 MCPDispatcher，后续消息即可正常使用。
        """
        tools = []
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            
            # 不等待 MCPHost 加载完成（避免用户消息被 MCP 服务器启动过程拖慢）
            mt = mgr.get_tools()
            if mt:
                print(f"[AI] 🔌 从 MCP 加载 {len(mt)} 个工具:")
                for t in mt:
                    fn = t.get("function", {})
                    print(f"       - {fn.get('name')}: {fn.get('description')[:60]}")
            else:
                print(f"[AI] ⚠️ MCP 工具为空 (_clients={list(mgr._clients.keys())}, _loading={mgr._loading})")
            tools.extend(mt)
        except Exception as e:
            print(f"[AI] ❌ 获取 MCP 工具失败: {e}")
        return tools

    # ==========================================
    # MCP 服务器状态注入
    # ==========================================
    
    def _inject_mcp_server_context(self):
        """
        将 MCP 服务器运行状态注入到 system prompt
        让 AI 知晓当前有哪些 MCP 服务器在线及其可用工具

        不阻塞等待 MCP 后台加载：仅注入当前状态快照。
        """
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            
            # 不等待 MCPHost 加载完成：仅注入当前已上线的服务器状态快照，
            # 避免 MCP 服务器启动过程拖慢用户消息响应。
            servers = mgr.get_all_servers()
            online_servers = [s for s in servers if s.get("online")]
            all_servers = [s for s in servers if s.get("enabled", True)]
            
            if not all_servers:
                return
            
            lines = ["\n\n## MCP 服务器状态"]
            for s in all_servers:
                status = "✅ 在线" if s.get("online") else "❌ 离线"
                tools_info = ""
                host = mgr._clients.get(s["id"])
                if host:
                    tool_names = [t.name for t in host.list_tools()]
                    if tool_names:
                        tools_info = f" [工具: {', '.join(tool_names)}]"
                lines.append(f"- `{s['id']}`: {status}{tools_info}")
            
            context = "\n".join(lines)
            # 追加到 system prompt，避免重复注入
            if context not in self._system_prompt:
                enhanced = self._system_prompt + context
                self.set_system_prompt(enhanced)
                print(f"[AI] 📊 已注入 MCP 服务器状态 ({len(online_servers)}/{len(all_servers)} 在线)")
        except Exception as e:
            print(f"[AI] ⚠️ 注入 MCP 服务器状态失败: {e}")

    # ==========================================
    # 工具函数
    # ==========================================
    
    def estimate_tokens(self, text: str) -> int:
        """估算 token 数量"""
        if self.stream_handler:
            return self.stream_handler.estimate_tokens(text)
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return chinese_chars * 2 + other_chars