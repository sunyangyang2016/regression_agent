"""监控插件 - 系统监控：CPU/内存/磁盘/网络/进程详情"""
import asyncio
import json
import os
from plugins.base import BasePlugin


class MonitorPlugin(BasePlugin):
    """系统监控插件：采集并展示 CPU/内存/磁盘/网络/进程资源详情"""

    name = "monitor_plugin"
    version = "1.0.0"
    description = "系统监控：CPU、内存、磁盘、网络与进程资源详情"
    author = "系统"

    hook_handlers = {}
    # 初始浮窗宽度：三栏布局（网络 | 磁盘 | AI 结论）需要更宽；高度由内容自适应
    initial_size = {"width": 1100}

    CONFIG_NAME = "monitor_config.json"

    def __init__(self):
        super().__init__()
        self._cfg: dict = {}
        self._running = False

    def on_load(self):
        """加载配置 + 注册 MCP 监控结果观察者（观察者模式）"""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config", self.CONFIG_NAME
            )
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self._cfg = json.load(f) or {}
            else:
                self._cfg = {}
        except Exception as e:
            print(f"[MonitorPlugin] [WARN] 加载配置失败: {e}")
            self._cfg = {}

        # 订阅插件结果（plugin_result）— 经 PluginBus，插件不依赖 MCPDispatcher
        try:
            from core.plugin_bus import PluginBus
            from .model.monitor_observer import MonitorObserver

            self._mcp_observer = MonitorObserver()
            PluginBus.subscribe("plugin_result", self._mcp_observer.update)
            print("[MonitorPlugin] ✅ 已订阅 plugin_result（经 PluginBus）")
        except Exception as e:
            print(f"[MonitorPlugin] ⚠️ 订阅 plugin_result 失败: {e}")

    async def run(self, context=None):
        """插件异步入口 - 轻量常驻循环"""
        self._running = True
        print("[MonitorPlugin] [START] run() 已启动（系统监控）")
        try:
            while self._running and self._enabled:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        finally:
            print("[MonitorPlugin] [STOP] run() 已停止")

    def exit(self):
        """插件退出 - 禁用/卸载时调用，清理资源"""
        self._running = False
        self._cfg = {}
        print("[MonitorPlugin] [EXIT] exit() 已调用（资源已清理）")

    # ==========================================
    # 配置读取（供 PluginBridge.getPluginConfig 调用）
    # ==========================================

    def get_config(self) -> dict:
        """返回当前生效配置"""
        return dict(self._cfg)

    def set_config(self, cfg: dict) -> bool:
        """更新并保存配置（保存到插件目录 config/monitor_config.json）"""
        try:
            self._cfg = cfg or {}
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config", self.CONFIG_NAME
            )
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"[MonitorPlugin] [ERROR] 保存配置失败: {e}")
            return False