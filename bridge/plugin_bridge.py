"""
PluginBridge - 插件管理桥接
处理插件列表、启用/禁用等前端交互
"""
import json
from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase


class PluginBridge(BridgeBase):
    """插件管理桥接 — 插件列表 / 启用 / 禁用"""

    # ==========================================
    # 前端 → 后端（通过 @pyqtSlot 暴露给 JS）
    # ==========================================

    @pyqtSlot(result=str)
    def getPlugins(self):
        """获取插件列表（供前端插件面板展示真实状态）"""
        try:
            pm = self.app_controller.plugin_manager
            if pm:
                return json.dumps(pm.get_metadata_list(), ensure_ascii=False)
        except Exception as e:
            print(f"[PluginBridge] getPlugins 失败: {e}")
        return "[]"

    @pyqtSlot(str, str, result=str)
    def togglePlugin(self, name, enable):
        """启用/禁用插件（enable: "true"/"false"）"""
        try:
            pm = self.app_controller.plugin_manager
            if not pm:
                return json.dumps({"ok": False, "message": "插件系统未初始化"}, ensure_ascii=False)
            if enable == "true":
                ok = pm.enable(name)
            else:
                ok = pm.disable(name)
            return json.dumps({"ok": ok, "name": name}, ensure_ascii=False)
        except Exception as e:
            print(f"[PluginBridge] togglePlugin 失败: {e}")
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def getPluginConfig(self, name=""):
        """获取插件配置（默认返回安全插件配置）"""
        try:
            pm = self.app_controller.plugin_manager
            if pm:
                plugin_name = name or "security_plugin"
                plugin = pm.get(plugin_name)
                if plugin and hasattr(plugin, "get_config"):
                    return json.dumps(plugin.get_config(), ensure_ascii=False)
        except Exception as e:
            print(f"[PluginBridge] getPluginConfig 失败: {e}")
        return "{}"