"""安全插件桥接层 - JS <-> Python 通信"""
import json
from PyQt5.QtCore import QObject, pyqtSlot
from ..controller import security_controller


class SecurityBridge(QObject):
    """供前端 security.js 调用的 QWebChannel 桥"""

    @pyqtSlot(result=str)
    def getConfig(self):
        try:
            return json.dumps(security_controller.get_config(), ensure_ascii=False)
        except Exception as e:
            print(f"[SecurityBridge] [ERROR] getConfig: {e}")
            return "{}"

    @pyqtSlot(str, result=str)
    def saveConfig(self, cfg_json):
        try:
            cfg = json.loads(cfg_json or "{}")
            ok = security_controller.save_config(cfg)
            return json.dumps({"ok": ok}, ensure_ascii=False)
        except Exception as e:
            print(f"[SecurityBridge] [ERROR] saveConfig: {e}")
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)