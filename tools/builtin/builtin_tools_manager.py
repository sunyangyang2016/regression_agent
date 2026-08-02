"""
内建工具管理器 — 独立于 MCP
支持工具箱模式：一个目录包含多个工具函数
"""
import os
import json
import importlib

from config.user_config import USER_DIR, resolve_config_path

# 用户配置写入目录：user_config/user/（默认配置在 defaults/ 下，只读不修改）
_CONFIG_PATH = os.path.join(USER_DIR, "builtin_tools_config.json")


class BuiltinManager:
    """内建工具管理器 — 扫描、注册、执行一体"""

    def __init__(self, functions_dir: str = None):
        base = os.path.dirname(os.path.abspath(__file__))
        self._functions_dir = functions_dir or os.path.join(base, "functions")
        self._tool_handlers: dict = {}
        self._tools: list = []
        self._loaded = False

    # ==========================================
    # 内部方法
    # ==========================================

    def _get_read_path(self):
        """读取路径：优先 user/ 目录，回退 defaults/ 目录"""
        return resolve_config_path("builtin_tools_config.json")

    def _read_config(self):
        """读取已启用工具列表：优先 user/，回退 defaults/（defaults 不被修改）"""
        try:
            path = self._get_read_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    return cfg.get("enabled_tools", [])
        except:
            pass
        return []

    def _write_config(self, enabled_tools: list):
        """写入已启用工具列表到 user/ 目录（defaults 目录不被修改）"""
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"enabled_tools": enabled_tools}, f, ensure_ascii=False, indent=2)

    def _load_module(self, mod_name):
        try:
            return importlib.import_module(f"tools.builtin.functions.{mod_name}")
        except Exception as e:
            print(f"[ToolsManager] ⚠️ 导入 {mod_name}.py 失败: {e}")
            return None

    # ==========================================
    # 公共方法
    # ==========================================

    def get_tools_for_api(self) -> list:
        """获取已启用的工具定义（从 .py 文件加载 TOOLS 列表）"""
        self._tools = []
        self._tool_handlers = {}

        enabled_list = self._read_config()
        if not enabled_list:
            print("[ToolsManager] ⚠️ 没有启用任何工具，不传递工具给 AI")
            return []

        enabled_set = set(enabled_list)

        if not os.path.isdir(self._functions_dir):
            return []

        for fname in sorted(os.listdir(self._functions_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            mod_name = fname[:-3]  # 去掉 .py
            mod = self._load_module(mod_name)
            if not mod:
                continue

            # 读取 TOOLS 列表
            tools_list = getattr(mod, "TOOLS", [])
            matched = []
            for t in tools_list:
                tname = t.get("function", {}).get("name", "")
                if tname in enabled_set:
                    matched.append(t)

            if not matched:
                continue

            self._tools.extend(matched)
            for t in matched:
                tname = t["function"]["name"]
                # 先找 exec_{name}，再找 {name}，兼容两种命名方式
                handler = getattr(mod, f"exec_{tname}", None) or getattr(mod, tname, None)
                if handler:
                    self._tool_handlers[tname] = handler

        tool_names = sorted(self._tool_handlers.keys())
        print(f"[ToolsManager] ✅ 加载 {len(self._tools)} 个内建工具: {', '.join(tool_names)}")
        return list(self._tools)

    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """执行内建工具（只有已启用的工具才能执行）"""
        enabled_list = self._read_config()
        if tool_name not in enabled_list:
            return f"⚠️ 工具 '{tool_name}' 未启用，请在工具面板中启用后使用"

        # 懒加载：如果未初始化或缓存为空，先加载
        if not self._tool_handlers:
            self.get_tools_for_api()

        handler = self._tool_handlers.get(tool_name)
        if handler:
            try:
                return handler(arguments)
            except Exception as e:
                return f"❌ 工具执行失败: {str(e)}"

        return f"⚠️ 工具 '{tool_name}' 未实现处理器"

    def cleanup(self):
        self._tool_handlers.clear()
        self._tools.clear()