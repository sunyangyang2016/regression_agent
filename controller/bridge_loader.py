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

    @staticmethod
    def _extract_log_modal_html():
        """从独立日志模块 view/html/chat_log.html 中提取 #logModal 悬浮窗结构

        日志模块已独立为 html/chat_log.html / css/chat_log.css / js/chat_log.js。
        由于应用是单页架构（setHtml 加载 index.html），在这里将
        #logModal 结构合并注入到 index.html。
        使用 <!-- START_LOG_MODAL --> 与 <!-- END_LOG_MODAL --> 标记定位。
        """
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        chat_log_path = os.path.join(base, "view", "html", "chat_log.html")
        try:
            with open(chat_log_path, "r", encoding="utf-8") as f:
                content = f.read()
            start_marker = "<!-- START_LOG_MODAL -->"
            end_marker = "<!-- END_LOG_MODAL -->"
            start_idx = content.find(start_marker)
            end_idx = content.find(end_marker)
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                return content[start_idx:end_idx + len(end_marker)].strip()
        except Exception as e:
            print(f"{LOG} ⚠️ 读取 view/html/chat_log.html 失败: {e}")
        return None

    def _load_page(self, webview):
        """读取自包含的 index.html（合并日志悬浮窗）并通过 setHtml 注入"""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        html_path = os.path.join(base, "view", "index.html")
        
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        
        # 合并日志悬浮窗结构：从独立日志模块 chat_log.html 提取 #logModal 注入到 index.html
        if "id=\"logModal\"" not in html:
            modal_html = self._extract_log_modal_html()
            if modal_html:
                html = html.replace("</body>", modal_html + "\n</body>")
                print(f"{LOG} 🪟 已注入日志悬浮窗 (#logModal) 从 chat_log.html")
            else:
                print(f"{LOG} ⚠️ 未能注入日志悬浮窗（chat_log.html 提取失败）")
        
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