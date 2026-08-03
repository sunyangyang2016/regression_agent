"""
插件加载器 - 动态加载插件模块
插件目录结构：plugins/builtin/<插件名>/main.py
"""
import os
import importlib.util
import inspect
from typing import List
from plugins.base import BasePlugin


class PluginLoader:
    """插件加载器"""

    def __init__(self, plugin_dirs: List[str] = None):
        if plugin_dirs is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            plugin_dirs = [os.path.join(base, "plugins", "builtin")]
        self.plugin_dirs = plugin_dirs

    def load_from_dir(self, directory: str) -> List[BasePlugin]:
        """从目录加载插件

        目录结构约定：
        plugins/builtin/<插件名>/main.py   ← 插件主类定义处
        """
        plugins = []
        if not os.path.exists(directory):
            return plugins

        for entry in sorted(os.listdir(directory)):
            entry_path = os.path.join(directory, entry)
            # 跳过非目录项（普通文件）
            if not os.path.isdir(entry_path):
                continue
            # 跳过缓存/隐藏目录（如 __pycache__）
            if entry.startswith("__") or entry.startswith("."):
                continue
            main_file = os.path.join(entry_path, "main.py")
            if not os.path.exists(main_file):
                print(f"[PluginLoader] 跳过插件目录 '{entry}'（缺少 main.py）")
                continue
            try:
                # 以目录名作为模块名动态加载 main.py
                mod_path = main_file
                spec = importlib.util.spec_from_file_location(entry, mod_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    for name, obj in inspect.getmembers(mod):
                        if (inspect.isclass(obj) and issubclass(obj, BasePlugin)
                                and obj is not BasePlugin and not inspect.isabstract(obj)):
                            instance = obj()
                            plugins.append(instance)
            except Exception as e:
                print(f"[PluginLoader] 加载插件目录 '{entry}' 失败: {e}")
        return plugins

    def load_all(self) -> List[BasePlugin]:
        """从所有目录加载插件"""
        plugins = []
        for directory in self.plugin_dirs:
            plugins.extend(self.load_from_dir(directory))
        return plugins