"""监控插件"""
import asyncio
from plugins.base import BasePlugin


class MonitorPlugin(BasePlugin):
    name = "monitor_plugin"
    version = "1.0.0"
    description = "系统监控"
    author = "系统"

    hook_handlers = {}

    def on_load(self):
        pass

    async def run(self, context=None):
        while self._enabled:
            await asyncio.sleep(5)

    def exit(self):
        pass