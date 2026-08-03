"""
插件基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BasePlugin(ABC):
    """插件基类 - 所有插件必须继承此类"""

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = []
    hooks: List[str] = []
    # 声明：本插件需要 hook 的事件 → 本插件内的处理方法
    # handler 统一签名：handler(payload_json: str) -> str(JSON)
    hook_handlers: Dict[str, str] = {}

    def __init__(self):
        self._enabled = True
        self._config: Dict[str, Any] = {}
        self._manager = None  # 由 PluginManager 在加载时注入

    @abstractmethod
    def on_load(self):
        """插件加载时调用"""
        ...

    @abstractmethod
    async def run(self, context=None):
        """插件异步入口 - 每次加载完成后由 PluginManager 自动异步启动。
        所有插件的 main.py 必须实现此方法。"""
        ...

    @abstractmethod
    def exit(self):
        """插件退出 - 插件禁用/卸载时调用，用于清理资源、停止后台任务。
        所有插件的 main.py 必须实现此方法。"""
        ...

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def on_enable(self):
        """插件启用时调用"""
        pass

    def on_disable(self):
        """插件禁用时调用"""
        pass

    def _get_ui_base_name(self) -> str:
        """计算插件 UI 素材的基础前缀：security_plugin -> security"""
        return self.name[:-len("_plugin")] if self.name.endswith("_plugin") else self.name

    def get_config_ui(self) -> Dict[str, str]:
        """返回插件自身配置界面素材（供前端浮层注入）。
        约定目录结构：
          plugins/builtin/<name>/index.html          <- 取 <body> 内片段 -> html
          plugins/builtin/<name>/view/css/<base>.css <- 全文 -> css（兼容 <name>.css）
          plugins/builtin/<name>/view/js/<base>.js   <- 全文 -> js
        返回字典: {"html": str, "css": str, "js": str}
        """
        import os

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdir = os.path.join(base, "plugins", "builtin", self.name)
        html = css = js = ""

        idx_path = os.path.join(pdir, "index.html")
        if os.path.exists(idx_path):
            try:
                with open(idx_path, "r", encoding="utf-8") as f:
                    h = f.read()
                beg = h.find("<body")
                body_start = h.find(">", beg) + 1 if beg != -1 else -1
                body_end = h.rfind("</body>")
                if beg != -1 and body_start != -1 and body_end > body_start:
                    frag = h[body_start:body_end].strip()
                    frag = _strip_ui_tags(frag)
                    html = frag
            except Exception:
                html = ""

        base_name = self._get_ui_base_name()
        css_path = os.path.join(pdir, "view", "css", f"{self.name}.css")
        if not os.path.exists(css_path):
            css_path = os.path.join(pdir, "view", "css", f"{base_name}.css")
        if os.path.exists(css_path):
            try:
                with open(css_path, "r", encoding="utf-8") as f:
                    css = f.read()
            except Exception:
                css = ""

        js_path = os.path.join(pdir, "view", "js", f"{self.name}.js")
        if not os.path.exists(js_path):
            js_path = os.path.join(pdir, "view", "js", f"{base_name}.js")
        if os.path.exists(js_path):
            try:
                with open(js_path, "r", encoding="utf-8") as f:
                    js = f.read()
            except Exception:
                js = ""

        return {"html": html, "css": css, "js": js}

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "enabled": self._enabled,
            "hook_handlers": list(self.hook_handlers.keys()),
            "config_ui": self.get_config_ui(),
        }


def _strip_ui_tags(frag: str) -> str:
    """移除 html 片段中的 <link>/<script> 外链标签（注入场景不需要）"""
    import re
    frag = re.sub(r"<link[^>]*>", "", frag)
    frag = re.sub(r"<script[^>]*>.*?</script>", "", frag, flags=re.S | re.I)
    return frag