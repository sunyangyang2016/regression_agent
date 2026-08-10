"""视频插件 - 学前教学视频中心：播放、下载、断点续播"""
import json
import os

from plugins.base import BasePlugin
from .model.video_observer import VideoObserver



class VideoPlugin(BasePlugin):
    """视频中心插件"""

    name = "video_plugin"
    version = "1.0.0"
    description = "学前教学视频中心：搜索、播放、下载、断点续播"
    author = "系统"
    initial_size = {"width": 1200}

    CONFIG_NAME = "video_config.json"

    def __init__(self):
        super().__init__()
        self._cfg: dict = {}
        self._observer = None

    def on_load(self):
        """加载配置 + 确保媒体目录存在 + 创建观察者"""
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
            print(f"[VideoPlugin] ⚠️ 加载配置失败: {e}")
            self._cfg = {}

        # 确保媒体目录存在（用户配置目录下）
        try:
            media_dir = os.path.join(os.getcwd(), "user_config", "media", "videos")
            os.makedirs(media_dir, exist_ok=True)
        except Exception:
            pass

        # ★ 创建观察者（监听命令文件 + 订阅 PluginBus）
        # observer 通过 get_bridge_instance() 获取 VideoBridge 单例（参照 monitor_plugin）
        if self._observer is None:
            try:
                self._observer = VideoObserver(bridge=None)
                print("[VideoPlugin] ✅ VideoObserver 已启动")
            except Exception as e:
                print(f"[VideoPlugin] ⚠️ VideoObserver 启动失败: {e}")

        print("[VideoPlugin] ✅ 已加载")

    async def run(self, context=None):
        """轻量常驻循环"""
        import asyncio
        while self._enabled:
            await asyncio.sleep(30)

    def exit(self):
        """插件退出 - 清理资源"""
        if self._observer:
            try:
                self._observer.stop()
            except Exception:
                pass
            self._observer = None
        self._cfg = {}
        print("[VideoPlugin] [EXIT] 已清理")

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
                os.path.dirname(os.path.abspath(__file__)), "config", self.CONFIG_NAME
            )
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"[VideoPlugin] [ERROR] 保存配置失败: {e}")
            return False