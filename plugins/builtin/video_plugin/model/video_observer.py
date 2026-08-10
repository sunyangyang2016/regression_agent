"""视频插件观察者 - 监听命令文件 + 订阅 PluginBus 事件"""
import json
import os
import threading
import time

from core.plugin_bus import PluginBus

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
# 命令文件路径（Skill 的 scripts 独立进程写入）
COMMANDS_FILE = os.path.join(_PROJECT_ROOT, "storage", "video_commands.json")


class VideoObserver:
    """视频观察者

    两个通道：
    1. 文件通道：Skill 的 scripts（独立进程）写入 video_commands.json → 本类读取执行
    2. 事件通道：主进程内 PluginBus.publish("video_control") → 本类直接订阅
    """

    # 已处理命令的时间戳集合（避免重复处理同一时间戳）
    _processed_ids = set()
    _max_processed = 100

    def __init__(self, bridge=None):
        self.bridge = bridge
        self._running = True
        self._last_mtime = 0.0

        # ★ 订阅 PluginBus 事件（主进程内直接通信）
        PluginBus.subscribe("video_control", self.on_control)
        PluginBus.subscribe("video_updated", self.on_updated)

        # 启动文件监听线程（独立进程 scripts 通道）
        self._file_thread = threading.Thread(target=self._file_loop, daemon=True)
        self._file_thread.start()

        print("[VideoObserver] ✅ 已启动（文件监听 + PluginBus 订阅）")

    # ==========================================
    # PluginBus 事件（主进程内直接通信）
    # ==========================================

    def on_control(self, payload):
        """AI 播放控制事件（主进程内）→ 直接控制前端播放器"""
        self._execute_control(payload)

    def on_updated(self, payload):
        """视频库更新事件（主进程内）→ 前端自动刷新"""
        self._refresh_frontend(payload)

    # ==========================================
    # 命令文件监听（独立进程 scripts 通道）
    # ==========================================

    def _file_loop(self):
        """后台线程：每 0.5 秒检查命令文件是否有新命令"""
        while self._running:
            try:
                if os.path.exists(COMMANDS_FILE):
                    mtime = os.path.getmtime(COMMANDS_FILE)
                    if mtime != self._last_mtime:
                        self._last_mtime = mtime
                        self._process_commands()
            except Exception as e:
                print(f"[VideoObserver] ⚠️ 文件监听异常: {e}")
            time.sleep(0.5)

    def _process_commands(self):
        """读取并执行命令文件中的所有命令，然后清空"""
        try:
            with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
                commands = json.load(f)
            if not isinstance(commands, list):
                return

            for cmd in commands:
                if not isinstance(cmd, dict):
                    continue
                cmd_type = cmd.get("type", "")
                if cmd_type == "video_control":
                    self._execute_control(cmd)
                elif cmd_type == "video_updated":
                    self._refresh_frontend(cmd)

            # 清空已处理的命令
            with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except (ValueError, OSError):
            pass
        except Exception as e:
            print(f"[VideoObserver] ⚠️ 处理命令失败: {e}")

    # ==========================================
    # 执行控制 / 刷新
    # ==========================================

    def _execute_control(self, payload: dict):
        """执行播放控制 → 前端 HTML5 播放器"""
        try:
            bridge = self.bridge or self._get_bridge()
            if bridge and hasattr(bridge, "execute_control"):
                bridge.execute_control(payload)
        except Exception as e:
            print(f"[VideoObserver] ⚠️ 播放控制失败: {e}")

    def _refresh_frontend(self, payload: dict):
        """刷新前端视频列表"""
        try:
            bridge = self.bridge or self._get_bridge()
            if bridge and hasattr(bridge, "refresh_frontend"):
                bridge.refresh_frontend(payload)
        except Exception as e:
            print(f"[VideoObserver] ⚠️ 刷新前端失败: {e}")

    def _get_bridge(self):
        """获取 VideoBridge 单例（延迟绑定）"""
        try:
            from ..bridge.video_bridge import get_bridge_instance
            return get_bridge_instance()
        except Exception:
            return None

    def stop(self):
        """停止监听"""
        self._running = False
        try:
            PluginBus.unsubscribe("video_control", self.on_control)
            PluginBus.unsubscribe("video_updated", self.on_updated)
        except Exception:
            pass
        print("[VideoObserver] ⏹ 已停止")