"""
插件管理器 - 统一管理插件的加载、启用、禁用
加载插件时将插件声明的 hook 处理函数自动注册到 HookRegistry；
卸载/禁用时自动清理对应 hook。
"""
import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.loader import PluginLoader
from plugins.hook_registry import HookRegistry
from plugins.dependency_resolver import DependencyResolver
from plugins.security import PluginSecurity


class PluginManager:
    """插件管理器"""

    def __init__(self):
        self.loader = PluginLoader()
        self.hooks = HookRegistry()
        self.dependency = DependencyResolver()
        self.security = PluginSecurity()
        self.context = None  # AppController 注入，供插件访问 app_controller / webview
        self._plugins: Dict[str, BasePlugin] = {}
        # 记录每个插件注册的 hook 事件名，用于卸载/禁用时清理
        self._plugin_hooks: Dict[str, Dict[str, Callable]] = {}
        # 记录每个插件异步 run 任务（插件名 → asyncio.Task）
        self._run_tasks: Dict[str, asyncio.Task] = {}

    def load_all(self) -> int:
        """加载所有插件，并自动注册插件声明的 hook 处理函数"""
        plugins = self.loader.load_all()
        # 验证安全
        for plugin in plugins:
            if not self.security.verify(plugin):
                print(f"[PluginManager] 插件安全验证失败: {plugin.name}")
                continue
            plugin._manager = self
            plugin.on_load()
            # 自动注册插件声明的 hook 到 HookRegistry
            registered = self._register_plugin_hooks(plugin)
            if registered:
                self._plugin_hooks[plugin.name] = registered
                print(f"[PluginManager] [OK] 插件 '{plugin.name}' 注册 hooks: {list(registered.keys())}")
            self._plugins[plugin.name] = plugin
            print(f"[PluginManager] [OK] 加载插件: {plugin.name} v{plugin.version}")
            # 加载完成自动异步启动插件的 run()
            self._start_run(plugin)
        return len(self._plugins)

    def _register_plugin_hooks(self, plugin: BasePlugin) -> Dict[str, Callable]:
        """将插件声明的 hook_handlers 注册到 HookRegistry，返回 {事件名: handler 引用}"""
        registered = {}
        for event, method_name in plugin.hook_handlers.items():
            handler = getattr(plugin, method_name, None)
            if handler:
                self.hooks.register(event, handler)
                registered[event] = handler
            else:
                print(f"[PluginManager] [WARN] 插件 '{plugin.name}' 声明 hook '{event}' 但缺少方法 '{method_name}'")
        return registered

    def _unregister_plugin_hooks(self, plugin: BasePlugin):
        """卸载插件时清理其注册的所有 hook（使用注册时保存的同一引用）"""
        handlers = self._plugin_hooks.pop(plugin.name, {})
        for event, handler in handlers.items():
            self.hooks.unregister(event, handler)

    # ==========================================
    # run / exit 生命周期管理
    # ==========================================

    def _start_run(self, plugin: BasePlugin):
        """自动异步启动插件的 run()（复用 HookRegistry 后台事件循环）"""
        try:
            loop = self.hooks._get_loop()
            task = loop.create_task(self._safe_run(plugin))
            self._run_tasks[plugin.name] = task
            print(f"[PluginManager] [START] 插件 '{plugin.name}' run() 已异步启动")
        except Exception as e:
            print(f"[PluginManager] [WARN] 启动插件 '{plugin.name}' run() 失败: {e}")

    async def _safe_run(self, plugin: BasePlugin):
        """包装 run，捕获异常避免后台任务崩溃"""
        try:
            await plugin.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[PluginManager] [WARN] 插件 '{plugin.name}' run() 异常: {e}")

    def _stop_run(self, plugin: BasePlugin):
        """取消插件的 run 任务"""
        task = self._run_tasks.pop(plugin.name, None)
        if task and not task.done():
            task.cancel()
            print(f"[PluginManager] [STOP] 插件 '{plugin.name}' run() 已取消")

    def _call_exit(self, plugin: BasePlugin):
        """调用插件的 exit()（禁用/卸载时清理资源和后台任务）"""
        try:
            plugin.exit()
            print(f"[PluginManager] [EXIT] 插件 '{plugin.name}' exit() 已调用")
        except Exception as e:
            print(f"[PluginManager] [WARN] 插件 '{plugin.name}' exit() 异常: {e}")

    # ==========================================
    # 加载 / 生命周期
    # ==========================================

    def enable(self, name: str) -> bool:
        """启用插件（重新注册 hooks，并重新异步启动 run）"""
        plugin = self._plugins.get(name)
        if plugin and not plugin._enabled:
            plugin._enabled = True
            plugin.on_enable()
            # 启用时重新注册 hook
            registered = self._register_plugin_hooks(plugin)
            if registered:
                self._plugin_hooks[name] = registered
            # 启用时重新异步启动 run
            self._start_run(plugin)
            self.hooks.trigger("plugin:enabled", json.dumps({"name": name}))
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用插件（调用 exit 清理资源，取消 run 任务，清理 hooks）"""
        plugin = self._plugins.get(name)
        if plugin and plugin._enabled:
            plugin._enabled = False
            plugin.on_disable()
            # 禁用时调用 exit 清理资源和后台任务
            self._call_exit(plugin)
            # 取消 run 任务
            self._stop_run(plugin)
            # 禁用时清理其注册的 hook
            self._unregister_plugin_hooks(plugin)
            self.hooks.trigger("plugin:disabled", json.dumps({"name": name}))
            return True
        return False

    def unload(self, name: str) -> bool:
        """卸载插件（调用 exit 清理资源，取消 run 任务，清理 hooks）"""
        plugin = self._plugins.pop(name, None)
        if plugin:
            # 卸载前调用 exit 清理资源和后台任务
            self._call_exit(plugin)
            # 取消 run 任务
            self._stop_run(plugin)
            # 卸载前清理 hook
            self._unregister_plugin_hooks(plugin)
            plugin.on_unload()
            self.hooks.trigger("plugin:unloaded", json.dumps({"name": name}))
            return True
        return False

    def get(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)

    def get_all(self) -> List[BasePlugin]:
        return list(self._plugins.values())

    def get_enabled(self) -> List[BasePlugin]:
        return [p for p in self._plugins.values() if p._enabled]

    @property
    def count(self) -> int:
        return len(self._plugins)

    def get_metadata_list(self) -> List[dict]:
        """获取所有插件的元数据列表（供前端展示）"""
        return [p.get_metadata() for p in self._plugins.values()]

    def get_bridge_objects(self) -> Dict[str, object]:
        """收集各插件自带 bridge 模块中的 QObject 实例，供前端 JS 通信。
        约定：插件 bridge 路径 plugins/builtin/<name>/bridge/<name>_bridge.py
        类名优先 <CamelCase>Bridge（如 SecurityBridge），回退 <Plugin>Bridge（如 SecurityPluginBridge）。
        动态加载前设置 __package__ 并将插件目录加入 sys.path，解决相对导入。
        加载前对源码执行安全扫描（复用 PluginSecurity.verify_source）。
        """
        import importlib
        import os
        import sys
        from importlib import util as _util

        bridges = {}
        _plugins_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in self._plugins:
            bridge_dir = os.path.join(_plugins_root, "plugins", "builtin", name, "bridge")
            if not os.path.isdir(bridge_dir):
                continue
            # 文件名兼容两种命名：<name>_bridge.py（security_plugin_bridge.py）与
            # 去 _plugin 后缀的 <base>_bridge.py（security_bridge.py）
            base = os.path.join(bridge_dir, f"{name}_bridge.py")
            if not os.path.exists(base):
                base_name = name[:-len("_plugin")] if name.endswith("_plugin") else name
                base = os.path.join(bridge_dir, f"{base_name}_bridge.py")
            if not os.path.exists(base):
                continue
            try:
                # 安全扫描：读取源码并校验危险模式
                with open(base, "r", encoding="utf-8") as f:
                    src = f.read()
                if not self.security.verify_source(src, name=f"{name}_bridge"):
                    print(f"[PluginManager] [WARN] 插件 bridge '{name}' 未通过安全扫描，拒绝注册")
                    continue

                spec = _util.spec_from_file_location(f"{name}_bridge", base)
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                # 设置包名和父路径，使 bridge 内的相对导入（如 from ..controller import ...）可用
                mod.__package__ = f"plugins.builtin.{name}.bridge"
                plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(base))))
                if plugin_root not in sys.path:
                    sys.path.insert(0, plugin_root)
                spec.loader.exec_module(mod)
                # 注册到 sys.modules：使插件内部（如 MonitorObserver）后续通过标准
                # 相对导入（from ..bridge.monitor_bridge import ...）复用同一模块对象，
                # 确保模块级单例状态（_bridge_instance）共享，避免双重加载导致 pushData 丢失
                _bridge_mod_name = os.path.splitext(os.path.basename(base))[0]
                _full_bridge_mod = f"{mod.__package__}.{_bridge_mod_name}"
                _existing = sys.modules.get(_full_bridge_mod)
                if _existing is None:
                    sys.modules[_full_bridge_mod] = mod
                else:
                    # 已由标准导入缓存：抛弃动态加载副本，改用缓存模块（避免双份实例）
                    mod = _existing

                # 类名推导：基于去 _plugin 后缀的基础名（如 security → SecurityBridge）
                # 优先 <BaseName>Bridge，回退 <BaseName>PluginBridge 与 <FullName>Bridge
                base_name_for_cls = name[:-len("_plugin")] if name.endswith("_plugin") else name
                cls_name = "".join(p.capitalize() for p in base_name_for_cls.split("_")) + "Bridge"
                cls = getattr(mod, cls_name, None)
                if cls is None:
                    cls_name2 = "".join(p.capitalize() for p in base_name_for_cls.split("_")) + "PluginBridge"
                    cls = getattr(mod, cls_name2, None)
                if cls is None:
                    cls_name3 = "".join(p.capitalize() for p in name.split("_")) + "Bridge"
                    cls = getattr(mod, cls_name3, None)
                if cls is None:
                    cls_name4 = "".join(p.capitalize() for p in name.split("_")) + "PluginBridge"
                    cls = getattr(mod, cls_name4, None)
                if cls:
                    bridge_key = (name[:-len("_plugin")] if name.endswith("_plugin") else name) + "_bridge"
                    # 仅对构造函数接受 webview 参数的 bridge 传入 webview（避免双重实例化与非 MonitorBridge 传参 TypeError）
                    import inspect as _inspect
                    try:
                        _sig = _inspect.signature(cls)
                        _accepts_webview = "webview" in _sig.parameters
                    except (TypeError, ValueError):
                        _accepts_webview = False
                    try:
                        if _accepts_webview:
                            bridges[bridge_key] = cls(webview=getattr(self.context, "webview", None))
                        else:
                            bridges[bridge_key] = cls()
                    except TypeError:
                        bridges[bridge_key] = cls()
            except Exception as e:
                print(f"[PluginManager] [WARN] 加载插件 bridge '{name}' 失败: {e}")
        return bridges
