"""
AppController - 应用主控制器
管理应用启动流程，协调 Model 与 View 的初始化
"""
import os
import sys
import json

# 全局补充 PATH：确保 Node.js/npx 在子进程中可用
_nodejs_path = r"C:\Program Files\nodejs"
if os.path.isdir(_nodejs_path) and _nodejs_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _nodejs_path + os.pathsep + os.environ["PATH"]

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QMainWindow, QDesktopWidget

from controller.bridge_manager import BridgeManager
from controller.bridge_loader import BridgeLoader
from core.event_bus import EventBus
LOG = "[AppController]"


class AppController(QObject):
    """应用主控制器"""

    def __init__(self, model_config, ai_client, parent=None):
        super().__init__(parent)
        self.model_config = model_config
        self.ai_client = ai_client

        from controller.ai_controller import AIController
        from model.services.conversation_model import ConversationModel
        from model.services.state_manager import AppStateManager
        self.ai_controller = AIController(ai_client, model_config)
        self.conversation_model = ConversationModel()
        self.state_manager = AppStateManager()

        from controller.chat_controller import ChatController
        self.chat_controller = ChatController(
            self.ai_controller, self.conversation_model, model_config
        )

        # ---- Plugin 系统初始化 ----
        from plugins.manager import PluginManager
        self.plugin_manager = PluginManager()
        self.plugin_manager.context = self  # 插件可访问 app_controller / webview

        # ---- Skill 系统初始化 ----
        from skills.manager import SkillManager
        from ai.skill_dispatcher import SkillDispatcher
        from skills.trigger_engine import TriggerEngine
        self.skill_manager = SkillManager()
        self.skill_dispatcher = SkillDispatcher()
        self.trigger_engine = TriggerEngine()
        # 是否将 MD 技能注册为 AI 可调用工具（默认开启；关闭则仅作为系统提示词注入）
        self.enable_md_skill_tools = True
        # 运行时同步 AI 工具时，跟踪已注册的 MD 技能工具名（skill_<name>），用于增删/启停后清理
        self._md_skill_tool_names: set = set()


        self.bridge_objects = {}
        # 插件自带 bridge 对象强引用缓存：QWebChannel.registerObject() 不持有所有权，
        # 若此处不保存，Python GC 回收后 JS 端访问会触发 C 级段错误（进程无痕消失）
        self._plugin_bridge_objects: dict = {}
        self.webview = None
        self.main_window = None 
        self.bridge_manager = None
        self.bridge_loader = None
        self._bridge = None  # ChatBridge 实例，用于信号连接
        self._ui_plugins = []
        self._initialized = False

    def _init_models(self):
        self.event_bus = EventBus()

    def create_main_window(self):
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
        window = QMainWindow()
        window.setWindowTitle("Regression Agent")
        window.resize(1400, 900)
        window.setMinimumSize(600, 450)
        screen = QDesktopWidget().screenGeometry()
        window.move((screen.width() - 1400) // 2, (screen.height() - 900) // 2)

        webview = QWebEngineView()
        webview.setZoomFactor(1.2)
        window.setCentralWidget(webview)
        self.webview = webview

        s = webview.settings()
        s.setAttribute(QWebEngineSettings.ErrorPageEnabled, False)
        s.setAttribute(QWebEngineSettings.PluginsEnabled, False)
        s.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.HyperlinkAuditingEnabled, False)

        window.setStyleSheet("""
            QMainWindow { background: #0a0d12; }
            QWebEngineView { background: transparent; }
        """)
        self.main_window = window
        return window

    def _register_bridge_objects(self):
        from bridge import ChatBridge, ModelBridge, ToolBridge, SkillBridge, MCPBridge, PluginBridge
        from bridge.agent_config_bridge import AgentConfigBridge

        main_bridge = ChatBridge(self)
        config_bridge = ModelBridge(self)
        tool_bridge = ToolBridge(self)
        skill_bridge = SkillBridge(self)
        mcp_bridge = MCPBridge(self)
        plugin_bridge = PluginBridge(self)
        agent_config_bridge = AgentConfigBridge(self)

        self._bridge = main_bridge  # 保存引用用于信号连接
        self.mcp_bridge = mcp_bridge  # 保存引用供 AI 调度器使用

        self.bridge_objects = {
            "py_bridge": main_bridge,
            "config_bridge": config_bridge,
            "tool_bridge": tool_bridge,
            "skill_bridge": skill_bridge,
            "mcp_bridge": mcp_bridge,
            "plugin_bridge": plugin_bridge,
            "agent_config_bridge": agent_config_bridge,
        }
        return main_bridge

    def _connect_signals(self):
        """连接 ChatController 信号到 ChatBridge 的 on_* 方法"""
        if not self._bridge:
            return
        cc = self.chat_controller

        # Controller 信号 → Bridge 的 JS 回调方法
        cc.update_message.connect(
            lambda mid, content: self._bridge.on_stream_update(content)
        )
        cc.complete_message.connect(
            lambda mid: self._bridge.on_stream_complete()
        )
        cc.set_processing.connect(
            lambda p: self._bridge.on_set_processing(p)
        )
        cc.show_error.connect(
            lambda msg: self._bridge.on_show_error(msg)
        )
        # 侧边栏列表更新时同步到前端（queue在主线程执行，防止AI线程冲突）
        self.conversation_model.conversation_list_changed.connect(
            lambda data: QTimer.singleShot(0, lambda: self._bridge.execute_js(
                f"renderChatList({json.dumps(data, ensure_ascii=False)});"
            ))
        )
        # 对话标题更新时同步到前端
        self.conversation_model.title_changed.connect(
            lambda cid, title: QTimer.singleShot(0, lambda: self._bridge.execute_js(
                f"document.getElementById('chatTitle').textContent={json.dumps(title, ensure_ascii=False)};"
            ))
        )

    def _on_bridge_ready(self):
        if self._initialized:
            return
        try:
            # 连接信号
            self._connect_signals()

            # 延迟初始化（让 UI 先渲染，避免卡住侧边栏显示）
            QTimer.singleShot(100, self._delayed_init)
            
            self._initialized = True
            print(f"{LOG} ✅ 所有组件初始化完成")
        except Exception as e:
            print(f"{LOG} ⚠️ 初始化异常: {e}")

    def _delayed_init(self):
        """延迟初始化（避免阻塞 UI）"""
        try:
            # 初始化插件系统（加载插件并注册 hook）
            # 幂等保护：若 start() 已预加载过（count > 0），此处不再重复加载，避免 hooks 重复注册/run 重复启动
            try:
                if self.plugin_manager.count == 0:
                    count = self.plugin_manager.load_all()
                    print(f"{LOG} 🔌 已加载 {count} 个插件")
                else:
                    print(f"{LOG} 🔌 插件已加载（{self.plugin_manager.count} 个），跳过重复加载")
            except Exception as e:
                print(f"{LOG} ⚠️ 加载插件失败: {e}")

            # 初始化技能系统
            self._init_skill_system()

            # 连接 AI 控制器
            self.ai_controller.connect()

            # 自动启动所有已安装的 MCP 服务器
            self._start_mcp_servers()

            for plugin in self._ui_plugins:
                try:
                    plugin.on_register()
                except Exception:
                    pass

            self._initialized = True
            print(f"{LOG} ✅ 所有组件初始化完成")
        except Exception as e:
            print(f"{LOG} ⚠️ 初始化异常: {e}")

    def _register_md_skill_tools(self) -> int:
        """将 MD 技能注册为可执行的技能适配器（供 AI 工具调用）"""
        count = 0
        try:
            adapters = self.skill_manager.loader.load_md_skill_adapters()
            for adapter in adapters:
                if self.skill_dispatcher.register_skill(adapter):
                    count += 1
        except Exception as e:
            print(f"[AppController] ⚠️ 注册 MD 技能适配器失败: {e}")
        return count

    def _init_skill_system(self):
        """初始化技能系统：加载技能并注册到调度器"""
        try:
            # 1. 加载技能（内建 Python 类）
            self.skill_manager.initialize()

            # 1.1 应用用户保存的内建技能启停配置（skills_config.json）
            applied = self.skill_manager.apply_builtin_skill_config()
            if applied:
                print(f"[AppController] 🎛️ 已应用 {applied} 个内建技能启停配置")

            # 2. 将已启用的 skill 注册到 SkillDispatcher
            count = self.skill_dispatcher.register_from_registry(
                self.skill_manager.registry
            )
            print(f"[AppController] 🎯 SkillDispatcher 已注册 {count} 个技能")

            # 2.1 将 MD 技能注册为可执行适配器（可配置）
            if self.enable_md_skill_tools:
                md_count = self._register_md_skill_tools()
                if md_count:
                    print(f"[AppController] 📄 已注册 {md_count} 个 MD 技能适配器")

            # 3. 初始化 TriggerEngine
            self.trigger_engine.set_skill_dispatcher(self.skill_dispatcher)
            self.trigger_engine.register_default_triggers()
            print(f"[AppController] 🔔 TriggerEngine 已配置 {self.trigger_engine.get_status()['keyword_triggers']} 个关键词触发器")
            # 3.1 注册技能声明的触发器（新增技能无需修改本方法）
            declared = self.trigger_engine.register_skills_triggers(
                self.skill_manager.registry.get_enabled()
            )
            if declared:
                print(f"[AppController] 🔔 已注册 {declared} 个技能声明式触发器")

            # 4. 注入 TriggerEngine 到 ChatController
            self.chat_controller.trigger_engine = self.trigger_engine

            # 5. 如果有 AI client，将 skill tool 描述注入
            if hasattr(self, 'ai_client') and self.ai_client:
                self.ai_client.skill_dispatcher = self.skill_dispatcher
                # 将 skill 工具描述注册到内建工具调度器
                self._register_skill_tools()

            # 6. 主动推送技能数据到前端
            self._sync_skills_to_frontend()
            # 7. 注入技能系统事件通道（可观测性：注册/注销/切换事件 -> EventBus）
            self.skill_manager.registry.set_event_sink(EventBus().emit)

        except Exception as e:
            print(f"[AppController] ⚠️ 技能系统初始化失败: {e}")

    def _get_skills_data(self) -> list:
        """直接从后端获取技能数据"""
        try:
            skills = []
            from skills.md_skill import MdSkill
            for s in self.skill_manager.registry.get_all():
                # MD 技能已注册为 MdSkill 适配器（供 AI 工具调用），避免与下方 MD 文件列表重复显示
                if isinstance(s, MdSkill):
                    continue
                # 获取完整元数据作为详情展示
                meta = {}
                try:
                    meta = s.get_metadata()
                except Exception:
                    pass
                skills.append({
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                    "enabled": s.enabled,
                    "source": "python",
                    "version": s.version,
                    "tags": s.tags,
                    "detail": {
                        "version": s.version,
                        "category": s.category,
                        "priority": meta.get("priority"),
                        "tags": s.tags,
                        "input_schema": meta.get("input_schema"),
                        "triggers": meta.get("triggers"),
                        "execution_count": meta.get("execution_count"),
                        "created_at": meta.get("created_at"),
                    },
                })
            from skills.manager import PROTECTED_MD_SKILLS
            for s in self.skill_manager.get_md_skills():
                skills.append({
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                    "category": "md",
                    "enabled": s.get("enabled", True),
                    "source": "markdown",
                    "version": "1.0.0",
                    "tags": [],
                    "protected": s.get("name", "") in PROTECTED_MD_SKILLS,
                    "detail": {
                        "content": s.get("content", ""),
                        "filepath": s.get("filepath", ""),
                        "skill_dir": s.get("skill_dir", ""),
                        "scripts": s.get("scripts", []),
                        "references": s.get("references", []),
                        "assets": s.get("assets", []),
                        "version": "1.0.0",
                        "category": "md",
                    },
                })
            return skills
        except Exception as e:
            print(f"[AppController] ⚠️ getSkillsData: {e}")
            return []

    def _sync_skills_to_frontend(self):
        """直接将技能数据注入到前端（绕过桥接调用）"""
        try:
            skills_data = json.dumps(self._get_skills_data(), ensure_ascii=False)
            js = (
                "if (typeof appState !== 'undefined' && appState) {\n"
                "    try {\n"
                "        appState.skills = " + skills_data + ";\n"
                "        if (typeof renderSkills === 'function') renderSkills();\n"
                "        console.log('[Skills] \u76F4\u63A5\u6CE8\u5165 ' + appState.skills.length + ' \u4E2A\u6280\u80FD');\n"
                "    } catch(e) { console.warn('[Skills] \u6CE8\u5165\u5931\u8D25:', e); }\n"
                "}"
            )
            if self._bridge:
                self._bridge.execute_js(js)

            # 延迟再推送一次（确保前端 panel 已加载完毕）
            skills_json = skills_data
            QTimer.singleShot(1500, lambda: self._execute_js_safe(
                "if (typeof appState !== 'undefined' && typeof renderSkills === 'function') {"
                "appState.skills = " + skills_json + "; renderSkills();"
                "console.log('[Skills] \u5EF6\u8FDF\u6CE8\u5165 ' + appState.skills.length + ' \u4E2A\u6280\u80FD');"
                "}"
            ))
        except Exception as e:
            print(f"[AppController] ⚠️ \u63A8\u9001\u6280\u80FD\u6570\u636E\u5931\u8D25: {e}")

    def _execute_js_safe(self, js_code: str):
        """安全执行 JS"""
        try:
            if self._bridge:
                self._bridge.execute_js(js_code)
        except Exception:
            pass

    def _register_skill_tools(self):
        """将 skill 工具注册到 AI 的 ToolDispatcher，使 AI 可调用 skill"""
        try:
            tool_descs = self.skill_dispatcher.get_tool_descriptions()
            if not tool_descs:
                print("[AppController] ⚠️ 没有 skill 工具可注册")
                return

            skill_disp = self.skill_dispatcher

            # 为每个 skill 注册一个 handler 到 ToolDispatcher
            for td in tool_descs:
                fn = td.get("function", {})
                skill_name = fn.get("name", "")
                if not skill_name:
                    continue

                # 从 "skill_xxx" 格式提取原始 skill 名称
                raw_name = skill_name.replace("skill_", "", 1) if skill_name.startswith("skill_") else skill_name

                # 注册异步 handler
                async def make_handler(args_dict, sn=raw_name):
                    args = args_dict or {}
                    return await skill_disp.execute_skill(sn, args)

                self.ai_client.tool_dispatcher.register(skill_name, make_handler)
                print(f"[AppController] ✅ Skill 工具已注册: {skill_name}")

            print(f"[AppController] 🚀 共注册 {len(tool_descs)} 个 skill 工具")

        except Exception as e:
            print(f"[AppController] ⚠️ 注册 skill 工具失败: {e}")

    def _register_one_skill_tool(self, skill_name: str):
        """注册单个 skill 的 AI 工具处理器"""
        if not self.ai_client:
            return
        tool_name = f"skill_{skill_name}"
        skill_disp = self.skill_dispatcher

        async def make_handler(args_dict, sn=skill_name):
            args = args_dict or {}
            return await skill_disp.execute_skill(sn, args)

        self.ai_client.tool_dispatcher.register(tool_name, make_handler)
        self._md_skill_tool_names.add(tool_name)
        print(f"[AppController] MD Skill 工具已注册: {tool_name}")

    def _unregister_one_skill_tool(self, skill_name: str):
        """移除单个 skill 的 AI 工具处理器"""
        if not self.ai_client:
            return
        tool_name = f"skill_{skill_name}"
        try:
            self.ai_client.tool_dispatcher.unregister(tool_name)
        except Exception:
            pass
        self._md_skill_tool_names.discard(tool_name)
        print(f"[AppController] 已移除 MD Skill 工具: {tool_name}")

    def _resync_md_skill_tools(self) -> int:
        """将磁盘上的 MD 技能同步到 AI（上传/删除/启停后调用）"""
        try:
            from skills.md_skill import MdSkill
            # 1. 清理当前已注册的 MD 适配器及其 AI 工具处理器（含启动时注册的）
            for skill in list(self.skill_dispatcher.registry.get_all()):
                if isinstance(skill, MdSkill):
                    self.skill_dispatcher.unregister_skill(skill.name)
                    self._unregister_one_skill_tool(skill.name)
            self._md_skill_tool_names.clear()

            # 2. 将磁盘状态同步到 SkillRegistry（注销失效技能，注册已启用技能）
            count = self.skill_manager.sync_md_skills_to_registry()

            # 3. 为每个已注册的 MD 技能注册 AI 工具处理器
            for skill in self.skill_dispatcher.registry.get_all():
                if isinstance(skill, MdSkill) and skill.enabled:
                    self._register_one_skill_tool(skill.name)

            if count:
                print(f"[AppController] 已同步 {count} 个 MD 技能到 AI")
            return count
        except Exception as e:
            print(f"[AppController] 同步 MD 技能到 AI 失败: {e}")
            return 0

    # ---- Python 内建技能 AI 工具同步 ----

    def _register_builtin_skill_tool(self, skill_name: str):
        """注册单个 Python 内建技能的 AI 工具处理器"""
        if not self.ai_client:
            return
        tool_name = f"skill_{skill_name}"
        skill_disp = self.skill_dispatcher

        async def make_handler(args_dict, sn=skill_name):
            args = args_dict or {}
            return await skill_disp.execute_skill(sn, args)

        self.ai_client.tool_dispatcher.register(tool_name, make_handler)
        print(f"[AppController] Skill 工具已注册: {tool_name}")

    def _resync_builtin_skill_tools(self) -> int:
        """将 Python 内建技能的启用状态同步到 AI（前端切换后调用）

        策略：先注销所有已注册的 Python 内建技能 handler，再按当前
        enabled 状态重新注册，确保与注册表状态一致。
        """
        try:
            from skills.md_skill import MdSkill
            # 1. 先清理所有 Python 内建技能的 AI 工具处理器
            if self.ai_client:
                for skill in self.skill_manager.registry.get_all():
                    if isinstance(skill, MdSkill):
                        continue
                    tool_name = f"skill_{skill.name}"
                    try:
                        self.ai_client.tool_dispatcher.unregister(tool_name)
                    except Exception:
                        pass
                # 2. 重新注册当前已启用的内建技能
                count = 0
                for skill in self.skill_manager.registry.get_all():
                    if isinstance(skill, MdSkill) or not skill.enabled:
                        continue
                    self._register_builtin_skill_tool(skill.name)
                    count += 1
                return count
            return 0
        except Exception as e:
            print(f"[AppController] 同步内建技能到 AI 失败: {e}")
            return 0

    def _start_mcp_servers(self):
        """MCP 服务器已由 MCPHost.__init__ 在后台线程中异步启动。
        这里只注册已在线服务器的工具到 AI 调度器，不阻塞主 UI。"""
        try:
            from tools.mcp.host import MCPHost
            mgr = MCPHost()
            registered_tools = 0

            for sid, client in list(mgr._clients.items()):
                if client and client.is_running():
                    tools = client.list_tools()
                    if tools and hasattr(self, 'ai_client') and self.ai_client:
                        mcp_disp = self.ai_client.mcp_dispatcher
                        for t in tools:
                            tool_name = t.name
                            async def make_handler(args_dict, tn=tool_name, cl=client):
                                args_dict = args_dict or {}
                                return cl.call_tool(tn, args_dict)
                            mcp_disp.register(tool_name, make_handler)
                            registered_tools += 1
                        print(f"{LOG} 📌 [{sid}] 注册 {len(tools)} 个工具到 MCP 调度器")

            if registered_tools > 0:
                print(f"{LOG} ✅ 注册 {registered_tools} 个工具")
            else:
                print(f"{LOG} 📌 MCP 后台加载中，工具后续自动注册")
        except Exception as e:
            print(f"{LOG} ⚠️ 注册 MCP 工具失败: {e}")

    def _on_bridge_failed(self, reason: str):
        print(f"{LOG} ⚠️ 桥接失败: {reason}")

    def start(self):
        self._init_models()
        window = self.create_main_window()

        self.bridge_manager = BridgeManager(self.webview)
        self.bridge_manager.bridge_ready.connect(self._on_bridge_ready)
        self.bridge_manager.bridge_failed.connect(self._on_bridge_failed)

        main_bridge = self._register_bridge_objects()
        self.bridge_manager.register_objects(self.bridge_objects)
        self.chat_controller.set_bridge(main_bridge)

        for plugin in self._ui_plugins:
            for name, obj in plugin.get_bridge_objects():
                self.bridge_manager.register_objects({name: obj})

        # 注册各插件自带的 bridge（JS <-> Python 通信）
        # 注意：必须在 load_all() 之后调用，get_bridge_objects() 依赖已加载的插件列表
        try:
            if self.plugin_manager.count == 0:
                plugin_count = self.plugin_manager.load_all()
                print(f"{LOG} 🔌 启动时预加载 {plugin_count} 个插件")
            plugin_bridges = self.plugin_manager.get_bridge_objects()
            if plugin_bridges:
                # 保存强引用：防止 Python GC 回收后 QWebChannel 持有悬空指针导致 C 级崩溃
                self._plugin_bridge_objects = plugin_bridges
                self.bridge_manager.register_objects(plugin_bridges)
                print(f"[AppController] [OK] 注册插件 bridge: {list(plugin_bridges.keys())}")
        except Exception as e:
            print(f"[AppController] [WARN] 注册插件 bridge 失败: {e}")

        window.show()

        self.bridge_loader = BridgeLoader()
        self.bridge_loader.load(
            webview=self.webview,
            channel=self.bridge_manager.channel,
            on_ready=self.bridge_manager.check_bridge_ready
        )
        return window

    def cleanup(self):
        print(f"{LOG} 🧹 开始清理资源...")
        if self.bridge_manager:
            try:
                self.bridge_manager.cleanup()
            except Exception:
                pass
        if self.ai_controller:
            try:
                self.ai_controller.cleanup()
            except Exception:
                pass
        for plugin in self._ui_plugins:
            try:
                plugin.on_unregister()
            except Exception:
                pass
        print(f"{LOG} ✅ 清理完成")