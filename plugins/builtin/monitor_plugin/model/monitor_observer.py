"""监控插件观察者（ConcreteObserver）——队列 + 后台线程处理 MCP 监控结果"""
import json
import os
import queue
import re
import threading
from datetime import datetime

# MCP 监控工具名前缀：仅完整快照工具写入/推送（部分字段工具如 get_disks/get_alerts
# 会破坏完整快照，不参与本链路；告警有独立 pushMonitorAlert/refreshAlerts 通道）
MONITOR_PREFIXES = (
    "get_all_stats",
    "get_system_stats",
)


# 模块级共享存储：observer 写入最新快照，monitor_bridge.getAll 读取（插件域内，无外部依赖）
_SNAPSHOT_STORE = {}
_SNAPSHOT_LOCK = threading.Lock()

# 告警队列文件（前端 refreshAlerts 每 5 秒轮询读取）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
ALERTS_FILE = os.path.join(_PROJECT_ROOT, "storage", "monitor_alerts.json")
# AI 回复事件标记前缀 → 处理方向（类似 MONITOR_PREFIXES，按前缀匹配 AI 回复文本）
AI_REPLY_MARKERS = {
    "{{CONCLUSION:": "conclusion",   # 结论 → 写快照 ai_judgment → 面板右侧「AI 监控结论」
    "{{ALERT:": "alert",             # 告警 → 写 monitor_alerts.json → 异常提醒面板
}


def get_latest_snapshot_json():
    """供 monitor_bridge 读取最新监控快照 JSON（线程安全）"""
    with _SNAPSHOT_LOCK:
        return _SNAPSHOT_STORE.get("latest")


def _write_snapshot_ai_judgment(text: str):
    """写入 AI 结论到共享快照的 ai_judgment 字段（供面板右侧结论区显示）"""
    try:
        with _SNAPSHOT_LOCK:
            store = dict(_SNAPSHOT_STORE)
        snap = store.get("latest")
        data = json.loads(snap) if snap else {}
        data["ai_judgment"] = text
        data["timestamp"] = datetime.now().isoformat()
        data["data_source"] = "remote"
        data_json = json.dumps(data, ensure_ascii=False)
        with _SNAPSHOT_LOCK:
            _SNAPSHOT_STORE["latest"] = data_json
        # 同时落盘快照文件，保证重启后面板仍能读到结论
        try:
            os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
            snapshot_file = os.path.join(_PROJECT_ROOT, "storage", "remote_monitor_data.json")
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # 触发前端刷新：pushData 内部 emit dataPushed → 前端重新 getAll → 结论区立即更新
        try:
            from ..bridge.monitor_bridge import get_bridge_instance
            mb = get_bridge_instance()
            if mb and hasattr(mb, "pushData"):
                mb.pushData(data_json)
        except Exception:
            pass
        print(f"[MonitorObserver] ✅ AI 结论已写入（{len(text)} 字符）")
    except Exception as e:
        print(f"[MonitorObserver] ⚠️ 写 AI 结论失败: {e}")


def _write_alert_file(alerts: list):
    """写入告警队列文件（保持最近 50 条）"""
    try:
        os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts[-50:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[MonitorObserver] ⚠️ 写告警队列失败: {e}")


class MonitorObserver:
    """观察者：update() 只入队（零阻塞广播线程），后台线程消费处理"""

    def __init__(self):
        self._queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()
        print("[MonitorObserver] 已启动（后台线程处理监控结果）")
        # 订阅 AI 回复事件：按标记前缀提取结论/告警（类似 MONITOR_PREFIXES 匹配工具名）
        try:
            from core.plugin_bus import PluginBus
            PluginBus.subscribe("ai_reply", self.on_ai_reply)
            print("[MonitorObserver] ✅ 已订阅 ai_reply（AI 结论/告警按标记提取）")
        except Exception as e:
            print(f"[MonitorObserver] ⚠️ 订阅 ai_reply 失败: {e}")

    # ---------- MCP 工具结果入口 ----------

    def update(self, tool_name, server_id, result_text):
        """Observer.update()：前缀匹配后仅入队，立即返回，不阻塞广播线程"""
        try:
            if not tool_name or not any(
                tool_name.startswith(p) for p in MONITOR_PREFIXES
            ):
                return
            self._queue.put((tool_name, server_id or "", result_text))
        except Exception as e:
            print(f"[MonitorObserver] 入队失败: {e}")

    def _run(self):
        """后台线程：解析结果 -> pushData 内存 -> exec_js 弹窗+渲染"""
        while True:
            tool_name, server_id, result_text = self._queue.get()
            try:
                if not result_text or result_text.startswith("X") or result_text.startswith("W"):
                    continue
                data = self._parse_json(result_text)
                if not data:
                    continue
                data["data_source"] = "remote"
                data.setdefault("remote_server", server_id)
                data_json = json.dumps(data, ensure_ascii=False)
                # 写入模块级共享存储（monitor_bridge.getAll 读取，插件域内）
                with _SNAPSHOT_LOCK:
                    _SNAPSHOT_STORE["latest"] = data_json
                # 同步写入 MonitorBridge 内存 + 发出 dataPushed 信号（前端自动弹窗+渲染）
                try:
                    # 注意：本文件位于 monitor_plugin/model/，bridge 是同级目录（monitor_plugin/bridge/），
                    # 需用两个点 ..bridge 上溯到 monitor_plugin 再进入 bridge
                    from ..bridge.monitor_bridge import get_bridge_instance
                    mb = get_bridge_instance()
                    if mb and hasattr(mb, "pushData"):
                        mb.pushData(data_json)
                except Exception as e:
                    print(f"[MonitorObserver] 通知 bridge 失败: {e}")
                    _SNAPSHOT_STORE["tool_name"] = tool_name
                    _SNAPSHOT_STORE["server_id"] = server_id
                print(f"[MonitorObserver] 快照已更新: {tool_name} ({server_id})")
            except Exception as e:
                print(f"[MonitorObserver] 处理失败: {e}")

    # ---------- AI 回复入口（按标记前缀提取结论/告警） ----------

    def on_ai_reply(self, content, session_id=""):
        """订阅 ai_reply：扫描 AI 完整回复，按 {{标记}} 提取结论 / 告警"""
        try:
            if not content or not isinstance(content, str):
                return
            for marker, kind in AI_REPLY_MARKERS.items():
                if marker not in content:
                    continue
                if kind == "conclusion":
                    text = self._extract_marker_value(content, "CONCLUSION")
                    if text:
                        _write_snapshot_ai_judgment(text)
                elif kind == "alert":
                    self._extract_alerts(content)
        except Exception as e:
            print(f"[MonitorObserver] ⚠️ 处理 AI 回复失败: {e}")

    @staticmethod
    def _extract_marker_value(content: str, name: str):
        """提取 {{NAME: 值}} 中的值（支持换行，取到下一个 }} 为止）"""
        m = re.search(r"\{\{\s*" + name + r"\s*:\s*(.*?)\}\}", content, re.S)
        if m:
            return m.group(1).strip()
        return None

    def _extract_alerts(self, content: str):
        """提取所有 {{ALERT: {json} }} 并追加写入告警队列"""
        alerts = []
        # 注意：ALERT 内是 JSON（含多层 {}），用贪婪匹配 \{.*\} 捕获完整 JSON 对象，
        # 再以结尾的 }} 作标记闭合；避免非贪婪在 JSON 首个 } 处提前截断
        for m in re.finditer(r"\{\{\s*ALERT\s*:\s*(\{.*\})\s*\}\}", content, re.S):
            raw = m.group(1).strip()
            try:
                alert = json.loads(raw)
            except Exception:
                continue
            if isinstance(alert, dict):
                alert.setdefault("timestamp", datetime.now().isoformat())
                alerts.append(alert)
        if not alerts:
            return
        try:
            existing = []
            if os.path.exists(ALERTS_FILE):
                with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        existing = data
            combined = existing + alerts
            _write_alert_file(combined)
            print(f"[MonitorObserver] ✅ 已写入 {len(alerts)} 条 AI 告警")
        except Exception as e:
            print(f"[MonitorObserver] ⚠️ 写 AI 告警失败: {e}")

    @staticmethod
    def _parse_json(text):
        """容错解析：先整体 JSON，失败则提取第一个 {...} 块"""
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
        return None