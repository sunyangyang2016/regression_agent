"""RAG 数据库插件 - 文档导入、向量化与本地知识库管理

MVC 结构（与 video_plugin 一致）：
  main.py        → RagPlugin（生命周期）
  bridge/        → RagBridge（QWebChannel 控制器，前端 JS 通信）
  model/         → RagService（业务逻辑，包装 rag_mcp_server 纯逻辑库）
  view/ + index  → 前端（rag.js / rag.css）
"""
import json
import os
import sys

# rag_mcp_server 已独立到 tools/mcp/server/rag-mcp-server/（宿主 main.py 已把该目录
# 加进 sys.path）。但 PluginLoader 加载本插件时只保证项目根在 sys.path，并不依赖宿主
# 入口——这里再兜底自举一次：无论以何种入口加载本插件，都能导入 rag_mcp_server。
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_RAG_SERVER_DIR = os.path.join(_APP_ROOT, "tools", "mcp", "server", "rag-mcp-server")
if _RAG_SERVER_DIR not in sys.path:
    sys.path.insert(0, _RAG_SERVER_DIR)

from plugins.base import BasePlugin
from .model.rag_service import RagService


class RagPlugin(BasePlugin):
    """RAG 数据库插件"""

    name = "rag_plugin"
    version = "1.0.0"
    description = "RAG 数据库：本地文档导入、向量化、检索管理"
    author = "系统"
    initial_size = {"width": 1100, "height": 720}

    CONFIG_NAME = "rag_config.json"

    def __init__(self):
        super().__init__()
        self._cfg: dict = {}

    def on_load(self):
        """加载插件配置 + 确保 RAG 数据目录存在"""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config", self.CONFIG_NAME)
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self._cfg = json.load(f) or {}
            else:
                self._cfg = {}
        except Exception as e:
            print(f"[RagPlugin] ⚠️ 加载配置失败: {e}")
            self._cfg = {}

        # 确保数据目录存在（user_config/rag/）
        try:
            from rag_mcp_server.config_manager import get_config_manager
            get_config_manager().ensure_dirs()
        except Exception as e:
            print(f"[RagPlugin] ⚠️ 数据目录初始化失败: {e}")

        print("[RagPlugin] ✅ 已加载")

    async def run(self, context=None):
        """轻量常驻循环"""
        import asyncio
        while self._enabled:
            await asyncio.sleep(30)

    def exit(self):
        """插件退出 - 停止导入并清理"""
        try:
            from .bridge.rag_bridge import get_bridge_instance
            bridge = get_bridge_instance()
            if bridge:
                bridge.stop_import()
        except Exception:
            pass
        self._cfg = {}
        print("[RagPlugin] [EXIT] 已清理")

    # ==========================================
    # 配置（供 PluginBridge.getPluginConfig 调用）
    # ==========================================

    def get_config(self) -> dict:
        return dict(self._cfg)

    def set_config(self, cfg: dict) -> bool:
        """更新并保存配置"""
        try:
            self._cfg = cfg or {}
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config", self.CONFIG_NAME)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"[RagPlugin] [ERROR] 保存配置失败: {e}")
            return False
