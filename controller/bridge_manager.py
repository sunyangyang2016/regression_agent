"""
BridgeManager - 桥接管理器
管理所有 WebChannel 桥接对象的生命周期
"""
import json
import time
from typing import Optional

from PyQt5.QtCore import QTimer, QObject, pyqtSignal


LOG = "[BridgeManager]"


class BridgeManager(QObject):
    """桥接管理器"""

    bridge_ready = pyqtSignal()
    bridge_failed = pyqtSignal(str)

    def __init__(self, webview, parent=None):
        super().__init__(parent)
        self.webview = webview
        self.channel = None
        self.bridge_ready_flag = False
        self._retry_count = 0
        self._max_retries = 30
        self._retry_delay = 200

    def check_bridge_ready(self):
        if not self.webview or not self.webview.page():
            return
        js_code = """
        JSON.stringify({
            ready: !!window._bridgeReady,
            has_py_bridge: !!window.py_bridge
        })
        """
        self.webview.page().runJavaScript(js_code, self._on_bridge_check)

    def _on_bridge_check(self, result: str):
        try:
            if result:
                data = json.loads(result)
                if data.get('ready') and data.get('has_py_bridge'):
                    self._handle_bridge_ready()
                    return
        except json.JSONDecodeError:
            pass
        self._retry_count += 1
        if self._retry_count < self._max_retries:
            if self._retry_count % 10 == 0:
                print(f"{LOG} ⏳ 等待桥接就绪 ({self._retry_count}/{self._max_retries})...")
            delay = min(self._retry_delay * (1.5 ** (self._retry_count // 10)), 2000)
            QTimer.singleShot(int(delay), self.check_bridge_ready)
        else:
            self._handle_bridge_failure("桥接超时")

    def _handle_bridge_ready(self):
        if not self.bridge_ready_flag:
            self.bridge_ready_flag = True
            print(f"{LOG} 🎉 桥接建立成功! (尝试 {self._retry_count} 次)")
            self.bridge_ready.emit()

    def _handle_bridge_failure(self, reason: str):
        print(f"{LOG} ⚠️ 桥接建立失败: {reason}")
        self.bridge_failed.emit(reason)

    def register_objects(self, objects: dict):
        from PyQt5.QtWebChannel import QWebChannel
        if not self.channel:
            self.channel = QWebChannel()
        for name, obj in objects.items():
            self.channel.registerObject(name, obj)
            print(f"{LOG} 💾 注册对象: {name}")

    def attach_to_page(self, page):
        if self.channel and page:
            try:
                page.setWebChannel(self.channel)
            except Exception:
                pass

    def cleanup(self):
        self.channel = None
        self.bridge_ready_flag = False