"""Git 集成插件"""
import asyncio
from plugins.base import BasePlugin


class GitPlugin(BasePlugin):
    name = "git_plugin"
    version = "1.0.0"
    description = "Git 集成"
    author = "系统"

    hook_handlers = {}

    def on_load(self):
        pass

    async def run(self, context=None):
        while self._enabled:
            await asyncio.sleep(5)

    def exit(self):
        pass