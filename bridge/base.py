"""
BridgeBase - 桥接基类
提供 JS 执行工具方法
"""
from PyQt5.QtCore import QObject


class BridgeBase(QObject):
    """桥接基类"""

    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller

    def execute_js(self, js_code: str):
        """执行 JS 代码（前端调用）"""
        try:
            if self.app_controller and self.app_controller.webview:
                self.app_controller.webview.page().runJavaScript(js_code)
        except Exception as e:
            print(f"[Bridge] ❌ JS 执行失败: {e}")