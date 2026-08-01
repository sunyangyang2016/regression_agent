"""
插件管理器 - 统一管理插件的加载、启用、禁用
"""
from typing import Any, Dict, List, Optional
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
        self._plugins: Dict[str, BasePlugin] = {}

    def load_all(self) -> int:
        """加载所有插件"""
        plugins = self.loader.load_all()
        # 验证安全
        for plugin in plugins:
            if not self.security.verify(plugin):
                print(f"[PluginManager] 插件安全验证失败: {plugin.name}")
                continue
            self._plugins[plugin.name] = plugin
        return len(self._plugins)

    def enable(self, name: str) -> bool:
        """启用插件"""
        plugin = self._plugins.get(name)
        if plugin and not plugin._enabled:
            plugin._enabled = True
            plugin.on_enable()
            self.hooks.trigger("plugin:enabled", name)
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用插件"""
        plugin = self._plugins.get(name)
        if plugin and plugin._enabled:
            plugin._enabled = False
            plugin.on_disable()
            self.hooks.trigger("plugin:disabled", name)
            return True
        return False

    def unload(self, name: str) -> bool:
        """卸载插件"""
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.on_unload()
            self.hooks.trigger("plugin:unloaded", name)
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