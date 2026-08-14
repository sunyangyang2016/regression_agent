"""视频插件观察者 - 监听 HTTP 命令 + 订阅 PluginBus 事件"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.plugin_bus import PluginBus

# Windows 控制台默认 GBK，emoji/中文打印会触发 UnicodeEncodeError，
# 独立导入本模块时兜底切到 UTF-8（主进程 main.py 已配置时无副作用）。
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream and _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
# 端口发现文件（脚本进程读取此文件定位命令端点）
PORT_FILE = os.path.join(_PROJECT_ROOT, "storage", "video_plugin.json")


class _VideoCommandHandler(BaseHTTPRequestHandler):
    """HTTP 命令端点：CLI 脚本（独立进程）POST /video_command → PluginBus.publish"""

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict) and payload.get("type") in ("video_control", "video_updated"):
                PluginBus.publish(payload["type"], payload)
                self._respond(200, {"ok": True})
            else:
                self._respond(400, {"ok": False, "error": "unknown payload type"})
        except Exception as e:
            print(f"[VideoObserver] ⚠️ 命令处理失败: {e}")
            self._respond(500, {"ok": False, "error": str(e)})

    def _respond(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        """静默默认请求日志"""
        pass


class VideoObserver:
    """视频观察者

    两个通道：
    1. HTTP 命令通道：Skill 的 scripts（独立进程）POST /video_command
       → 本类服务器 PluginBus.publish("video_control"/"video_updated") → 本类直接订阅
    2. 事件通道：主进程内 PluginBus.publish("video_control") → 本类直接订阅
    """

    def __init__(self, bridge=None):
        self.bridge = bridge
        self._running = True
        self._http_server = None

        # ★ 订阅 PluginBus 事件（命令最终都汇入事件总线）
        PluginBus.subscribe("video_control", self.on_control)
        PluginBus.subscribe("video_updated", self.on_updated)

        # 启动 HTTP 命令服务器（独立进程 scripts 通道）
        self._start_command_server()

        print("[VideoObserver] ✅ 已启动（HTTP 命令服务器 + PluginBus 订阅）")

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
    # HTTP 命令服务器（独立进程 scripts 通道）
    # ==========================================

    def _start_command_server(self):
        """启动 127.0.0.1 随机端口 HTTP 服务器，端口写入 storage/video_plugin.json"""
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), _VideoCommandHandler)
            self._http_server = server
            import threading
            threading.Thread(target=server.serve_forever, daemon=True).start()

            # 写端口发现文件（脚本进程读取）
            try:
                os.makedirs(os.path.dirname(PORT_FILE), exist_ok=True)
                with open(PORT_FILE, "w", encoding="utf-8") as f:
                    json.dump({"port": server.server_address[1]}, f)
            except Exception as e:
                print(f"[VideoObserver] ⚠️ 写端口文件失败: {e}")

            print(f"[VideoObserver] 🖥 HTTP 命令端点: http://127.0.0.1:{server.server_address[1]}/video_command")
        except Exception as e:
            print(f"[VideoObserver] ⚠️ HTTP 命令服务器启动失败: {e}")

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
            if self._http_server:
                self._http_server.shutdown()
                self._http_server.server_close()
                self._http_server = None
        except Exception:
            pass
        try:
            PluginBus.unsubscribe("video_control", self.on_control)
            PluginBus.unsubscribe("video_updated", self.on_updated)
        except Exception:
            pass
        print("[VideoObserver] ⏹ 已停止")
