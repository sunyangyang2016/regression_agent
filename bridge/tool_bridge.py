"""
ToolBridge - 工具桥接
处理内置工具的加载、开关、管理等前后端交互
"""
import json
import os
from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "user_config", "defaults", "builtin_tools_config.json"
)


class ToolBridge(BridgeBase):
    """工具桥接 — 内置工具管理"""

    def __init__(self, app_controller):
        super().__init__(app_controller)
        self._ensure_config()

    def _ensure_config(self):
        """确保配置文件存在"""
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        if not os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"enabled_tools": []}, f, ensure_ascii=False, indent=2)

    def _read_config(self):
        """读取工具开关配置"""
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"enabled_tools": []}

    def _write_config(self, config):
        """写入工具开关配置"""
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def _is_tool_enabled(self, name, config):
        """判断工具是否启用"""
        enabled = config.get("enabled_tools", [])
        return name in enabled

    def _load_builtin_tools(self):
        """从 functions/ 目录动态加载所有工具"""
        import importlib
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        func_dir = os.path.join(base_dir, "tools", "builtin", "functions")
        config = self._read_config()
        tools = []
        actual_names = set()
        if not os.path.exists(func_dir):
            return tools
        for fname in sorted(os.listdir(func_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            mod_name = fname[:-3]
            try:
                spec = importlib.util.spec_from_file_location(mod_name, os.path.join(func_dir, fname))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                continue
            tools_list = getattr(mod, "TOOLS", [])
            for t in tools_list:
                try:
                    fn = t.get("function", {})
                    display = t.get("display", {})
                    tool_name = fn.get("name", "")
                    if not tool_name:
                        continue
                    actual_names.add(tool_name)
                    params = fn.get("parameters", {})
                    props = params.get("properties", {})
                    required = params.get("required", [])
                    params_list = []
                    for pname, pinfo in props.items():
                        req_mark = "*" if pname in required else ""
                        ptype = pinfo.get("type", "string")
                        pdesc = pinfo.get("description", "")
                        params_list.append(f"  {req_mark}{pname} ({ptype}): {pdesc}")
                    params_info = "\n".join(params_list) if params_list else "无"
                    tools.append({
                        "name": tool_name,
                        "description": fn.get("description", ""),
                        "name_cn": display.get("name_cn", tool_name),
                        "description_cn": display.get("description_cn", ""),
                        "icon": display.get("icon", "fa-cog"),
                        "category": "builtin",
                        "enabled": self._is_tool_enabled(tool_name, config),
                        "parameters_info": params_info
                    })
                except Exception as e:
                    print(f"[ToolBridge] 解析 {mod_name} 失败: {e}")

        enabled = config.get("enabled_tools", [])
        cleaned = [t for t in enabled if t in actual_names]
        if len(cleaned) != len(enabled):
            config["enabled_tools"] = cleaned
            self._write_config(config)

        return tools

    @pyqtSlot(result=str)
    def getTools(self):
        """返回工具列表 JSON"""
        tools = self._load_builtin_tools()
        return json.dumps(tools, ensure_ascii=False)

    @pyqtSlot(str, bool, result=bool)
    def toggleTool(self, name, enabled):
        """切换工具开关状态"""
        try:
            config = self._read_config()
            enabled_list = config.setdefault("enabled_tools", [])
            if enabled:
                if name not in enabled_list:
                    enabled_list.append(name)
            else:
                if name in enabled_list:
                    enabled_list.remove(name)
            self._write_config(config)
            print(f"[ToolBridge] 工具 '{name}' 已{'启用' if enabled else '禁用'}")
            return True
        except Exception as e:
            print(f"[ToolBridge] 切换失败: {e}")
            return False

    @pyqtSlot(result=str)
    def listUtilityTools(self):
        """列出 utility 工具"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        utility_dir = os.path.join(base_dir, "tools", "utility")
        tools = []
        try:
            if os.path.exists(utility_dir):
                for tid in sorted(os.listdir(utility_dir)):
                    desc_path = os.path.join(utility_dir, tid, "description.json")
                    if os.path.exists(desc_path):
                        with open(desc_path, "r", encoding="utf-8") as f:
                            tools.append(json.load(f))
        except Exception as e:
            print(f"[ToolBridge] 读取 utility 失败: {e}")
        return json.dumps(tools)