"""
BridgeLoader - 桥接加载器
直接读取自包含的 index.html（所有面板内容内联），通过 setHtml 注入
"""
import os
import time

from PyQt5.QtCore import QTimer, QUrl


LOG = "[BridgeLoader]"


class BridgeLoader:
    """桥接加载器"""

    def __init__(self):
        self._retries = 0
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._webview = None
        self._channel = None
        self._on_ready = None
        self._main_start = 0.0
        self._loaded = False

    def load(self, webview, channel, on_ready=None):
        self._webview = webview
        self._channel = channel
        self._on_ready = on_ready
        self._retries = 0
        self._main_start = time.time()
        self._loaded = False
        webview.loadFinished.connect(self._on_page_loaded)
        self._load_page(webview)

    def _load_page(self, webview):
        """读取自包含的 index.html 并通过 setHtml 注入"""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        html_path = os.path.join(base, "view", "index.html")
        
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        
        print(f"{LOG} 直接加载 index.html ({len(html)} chars)")
        
        if self._channel and webview.page():
            try:
                webview.page().setWebChannel(self._channel)
            except Exception:
                pass
        
        webview.setHtml(html, QUrl.fromLocalFile(os.path.join(base, "view") + "/"))
        
        try: self._timer.timeout.disconnect()
        except TypeError: pass
        self._timer.timeout.connect(lambda: self._on_timeout(self._webview))
        self._timer.start(30000)

    def _on_page_loaded(self, ok):
        if self._loaded:
            return
        if ok:
            elapsed = time.time() - self._main_start
            print(f"{LOG} 页面加载完成 {elapsed:.3f}s")
            QTimer.singleShot(1000, self._check_bridge)
        else:
            print(f"{LOG} ⚠️ 页面加载失败")

    def _check_bridge(self):
        if self._loaded or not self._webview or not self._webview.page():
            return
        js = "JSON.stringify({ready:!!window._bridgeReady})"
        self._webview.page().runJavaScript(js, self._on_bridge_result)

    def _on_bridge_result(self, result):
        if self._loaded:
            return
        import json
        try:
            if result:
                data = json.loads(result)
                if data.get('ready'):
                    self._on_finished(True)
                    return
        except Exception:
            pass
        self._retries += 1
        if self._retries < 30:
            QTimer.singleShot(500, self._check_bridge)
        else:
            print(f"{LOG} ⚠️ 桥接超时")
            self._on_finished(False)

    def _on_timeout(self, webview):
        if self._loaded:
            return
        elapsed = time.time() - self._main_start if self._main_start else 0
        self._retries += 1
        print(f"{LOG} 超时 ({self._retries}/3) {elapsed:.1f}s")
        if self._retries >= 3:
            return
        self._load_page(webview)
        self._timer.start(15000)

    def _on_finished(self, ok):
        self._loaded = True
        elapsed = time.time() - self._main_start
        print(f"{LOG} 全部完成 {elapsed:.3f}s")
        if ok and self._on_ready:
            QTimer.singleShot(200, self._on_ready)