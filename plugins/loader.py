"""
插件加载器 - 动态加载插件模块
"""
import os
import importlib
import inspect
from typing import List, Optional
from plugins.base import BasePlugin


class PluginLoader:
    """插件加载器"""

    def __init__(self, plugin_dirs: List[str] = None):
        if plugin_dirs is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            plugin_dirs = [os.path.join(base, "plugins", "builtin")]
        self.plugin_dirs = plugin_dirs

    def load_from_dir(self, directory: str) -> List[BasePlugin]:
        """从目录加载插件"""
        plugins = []
        if not os.path.exists(directory):
            return plugins

        for fname in sorted(os.listdir(directory)):
            if fname.endswith(".py") and not fname.startswith("__"):
                mod_path = os.path.join(directory, fname)
                try:
                    spec = importlib.util.spec_from_file_location(
                        fname[:-3], mod_path
                    )
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        for name, obj in inspect.getmembers(mod):
                            if (inspect.isclass(obj) and issubclass(obj, BasePlugin)
                                    and obj is not BasePlugin and not inspect.isabstract(obj)):
                                instance = obj()
                                plugins.append(instance)
                except Exception as e:
                    print(f"[PluginLoader] 加载插件失败 {fname}: {e}")
        return plugins

    def load_all(self) -> List[BasePlugin]:
        """从所有目录加载插件"""
        plugins = []
        for directory in self.plugin_dirs:
            plugins.extend(self.load_from_dir(directory))
        return plugins