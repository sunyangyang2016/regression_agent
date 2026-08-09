"""监控插件桥接层 - JS <-> Python 通信（只读远程监控快照）"""
import json
import os
import time
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal


# 项目根目录（跳过 5 级: bridge -> monitor_plugin -> builtin -> plugins -> 根）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
# 远程监控数据快照文件（AI 通过 collect_stats.py 写入，插件只读）
SNAPSHOT_FILE = os.path.join(_PROJECT_ROOT, "storage", "remote_monitor_data.json")
# 提醒队列文件（AI 通过 push_alert.py 写入，插件只读）
ALERTS_FILE = os.path.join(_PROJECT_ROOT, "storage", "monitor_alerts.json")
# 快照有效期（秒）：超过 3 秒未更新视为过期/不可用
SNAPSHOT_TTL = 3.0


def read_alerts(max_items: int = 50) -> list:
    """读取提醒队列（最近 max_items 条）"""
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[-max_items:]
    except Exception as e:
        print(f"[MonitorBridge] ⚠️ 读取提醒队列失败: {e}")
    return []


def save_alert(alert: dict) -> bool:
    """保存单条异常提醒到队列文件（AI 工具调用入口）"""
    try:
        if not alert or not isinstance(alert, dict):
            return False
        if not alert.get("timestamp"):
            alert["timestamp"] = datetime.now().isoformat()
        queue = read_alerts(50)
        queue.append(alert)
        os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(queue[-50:], f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[MonitorBridge] ⚠️ 保存提醒失败: {e}")
        return False


def read_remote_snapshot() -> dict:
    """读取远程监控数据快照，判断有效性。"""
    try:
        if not os.path.exists(SNAPSHOT_FILE):
            return {"data_source": "unavailable", "error": "远程监控数据快照不存在"}
        mtime = os.path.getmtime(SNAPSHOT_FILE)
        if time.time() - mtime > SNAPSHOT_TTL:
            return {"data_source": "unavailable", "error": "远程监控数据快照已过期"}
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"data_source": "unavailable", "error": "快照格式错误"}
        data["data_source"] = "remote"
        return data
    except Exception as e:
        print(f"[MonitorBridge] ⚠️ 读取远程快照失败: {e}")
        return {"data_source": "error", "error": str(e)}


_bridge_instance = None


def get_bridge_instance():
    """供插件内部（observer 等）获取 MonitorBridge 单例"""
    return _bridge_instance


class MonitorBridge(QObject):
    """供前端 monitor.js 调用的 QWebChannel 桥（只读远程快照展示）"""

    dataPushed = pyqtSignal()  # 数据到达信号（前端自动弹窗/刷新通道）

    def __init__(self, parent=None, webview=None):
        super().__init__(parent)
        global _bridge_instance
        _bridge_instance = self
        self._webview = webview
        self._latest_data = None

    @pyqtSlot(str)
    def pushData(self, data_json):
        """MCP 监控工具返回的数据推送到内存，发出 dataPushed 信号。
        注意：不再自动弹出/切换监控面板，避免打断用户当前 Tab。"""
        try:
            self._latest_data = json.loads(data_json)
            self.dataPushed.emit()
            print("[MonitorBridge] ✅ pushData 已缓存并通知前端渲染")
        except Exception as e:
            print(f"[MonitorBridge] ⚠️ pushData 解析失败: {e}")

    @pyqtSlot(result=str)
    def getStats(self):
        try:
            return json.dumps(read_remote_snapshot(), ensure_ascii=False)
        except Exception as e:
            return '{"data_source":"error","error":"' + str(e) + '"}'

    @pyqtSlot(result=str)
    def getProcesses(self):
        try:
            data = self._get_snapshot()
            return json.dumps(data.get("processes", []), ensure_ascii=False)
        except Exception:
            return "[]"

    @pyqtSlot(str, result=str)
    def getProcessesLimit(self, max_count):
        try:
            count = int(max_count or 8)
            data = self._get_snapshot()
            return json.dumps(data.get("processes", [])[:count], ensure_ascii=False)
        except Exception:
            return "[]"

    @pyqtSlot(result=str)
    def getDisks(self):
        try:
            data = self._get_snapshot()
            return json.dumps(data.get("disks", []), ensure_ascii=False)
        except Exception:
            return "[]"

    def _get_snapshot(self) -> dict:
        """优先共享快照存储（observer 写入），回退自身内存/文件"""
        try:
            from .model.monitor_observer import get_latest_snapshot_json
            snap = get_latest_snapshot_json()
            if snap:
                return json.loads(snap)
        except Exception:
            pass
        if self._latest_data is not None:
            return self._latest_data
        return read_remote_snapshot()

    @pyqtSlot(result=str)
    def getAll(self):
        try:
            return json.dumps(self._get_snapshot(), ensure_ascii=False)
        except Exception as e:
            return '{"data_source":"error","error":"' + str(e) + '"}'

    @pyqtSlot(result=str)
    def getAlerts(self):
        try:
            if os.path.exists(ALERTS_FILE):
                with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return json.dumps(data[-50:], ensure_ascii=False)
            return "[]"
        except Exception:
            return "[]"

    @pyqtSlot()
    def clearAlerts(self):
        try:
            os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
            with open(ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False)
            print("[MonitorBridge] ✅ 已清空异常提醒队列")
        except Exception as e:
            print(f"[MonitorBridge] [ERROR] clearAlerts: {e}")