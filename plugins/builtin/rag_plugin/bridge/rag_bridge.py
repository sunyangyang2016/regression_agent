"""RAG 插件桥接层（MVC Controller）- JS <-> Python 通信

前端 rag.js 调用各 pyqtSlot → RagService（Model）执行；
后台线程（导入/统计/检索/下载）结果经 execute_js 推送 window.ragApp.* 回调。
"""
import json
import os
import threading
import time

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal

from ..model.rag_service import RagService
from rag_mcp_server.models import ImportOptions

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

_bridge_instance = None


def get_bridge_instance():
    """供插件内部（observer 等）获取 RagBridge 单例"""
    return _bridge_instance


class RagBridge(QObject):
    """供前端 rag.js 调用的 QWebChannel 桥"""

    # ★ 后台线程 → GUI 线程的 JS 执行通道（跨线程 QueuedConnection 自动 marshal）
    _jsRequested = pyqtSignal(str)

    # 记录表刷新节流（避免逐文件刷新刷爆前端）
    _RECORD_THROTTLE_SEC = 0.8

    def __init__(self, parent=None, webview=None):
        super().__init__(parent)
        global _bridge_instance
        _bridge_instance = self
        self._webview = webview
        self._jsRequested.connect(self._exec_js_on_gui)
        self._last_record_push = 0.0
        self._service = RagService(
            on_progress=self._push_progress,
            on_log=self._push_log,
            on_done=self._push_done,
            on_records_changed=self._notify_records_changed,
        )

    # ================================================================
    # 工具方法
    # ================================================================

    def execute_js(self, js_code: str):
        """★ 线程安全地执行前端 JS：后台线程 emit 信号 → GUI 线程 runJavaScript"""
        try:
            if self._webview:
                self._jsRequested.emit(js_code)
        except Exception as e:
            print(f"[RagBridge] JS 执行失败: {e}")

    def _exec_js_on_gui(self, js_code: str):
        """仅在 GUI 主线程执行（信号跨线程 QueuedConnection 自动 marshal）"""
        try:
            if self._webview:
                self._webview.page().runJavaScript(js_code)
        except Exception as e:
            print(f"[RagBridge] JS 执行失败: {e}")

    def stop_import(self):
        """供插件 exit 调用：停止正在进行的导入"""
        try:
            self._service.stop_import()
        except Exception as e:
            print(f"[RagBridge] 停止导入失败: {e}")

    # ================================================================
    # 推送前端（后台线程 → execute_js → GUI 线程执行 JS 回调）
    # ================================================================

    def _push_progress(self, done, total):
        self.execute_js("window.ragApp&&window.ragApp.importProgress&&"
                        "window.ragApp.importProgress(%d,%d);" % (int(done), int(total)))

    def _push_log(self, msg):
        self.execute_js("window.ragApp&&window.ragApp.importLog&&"
                        "window.ragApp.importLog(%s);" % json.dumps(str(msg), ensure_ascii=False))

    def _push_done(self, stats):
        self.execute_js("window.ragApp&&window.ragApp.importDone&&"
                        "window.ragApp.importDone(%s);" % json.dumps(stats, ensure_ascii=False))

    def _notify_records_changed(self):
        now = time.monotonic()
        if now - self._last_record_push < self._RECORD_THROTTLE_SEC:
            return
        self._last_record_push = now
        self.execute_js("window.ragApp&&window.ragApp.refreshRecords&&"
                        "window.ragApp.refreshRecords();")

    # ================================================================
    # 状态 / 配置
    # ================================================================

    @pyqtSlot(result=str)
    def getStatus(self):
        """轻量状态（同步返回 JSON）：运行中 / 模型就绪 / 记录计数"""
        try:
            return json.dumps(self._service.get_light_status(), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, str, result=str)
    def refreshStats(self, database, collection):
        """较重统计（目录扫描 + ChromaDB 集合计数）→ 后台线程 → 推 applyStats

        database: 统计哪个向量库；collection: 记录计数限定到哪个集合（空 = 全库）。
        """
        def _run():
            try:
                payload = self._service.refresh_stats(
                    database=(database or "").strip() or None,
                    collection=(collection or "").strip() or None)
            except Exception as e:
                payload = {"error": str(e)}
            self.execute_js("window.ragApp&&window.ragApp.applyStats&&"
                            "window.ragApp.applyStats(%s);"
                            % json.dumps(payload, ensure_ascii=False))
        threading.Thread(target=_run, daemon=True, name="rag-stats").start()

    @pyqtSlot(result=str)
    def getDefaults(self):
        """前端表单预填默认值"""
        try:
            return json.dumps(self._service.defaults(), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def getModelStatus(self):
        try:
            return json.dumps({
                "embedding": self._service.is_model_ready("embedding"),
                "rerank": self._service.is_model_ready("rerank"),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def setDatabase(self, name):
        """持久化当前向量数据库选择，返回 {ok}"""
        try:
            return json.dumps(self._service.set_database(name or ""), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def saveUiState(self, state_json):
        """持久化 RAG 插件 UI 表单状态（导入表单 + 状态栏上下文）到 user/rag_config.json"""
        try:
            data = json.loads(state_json or "{}")
        except Exception:
            data = {}
        try:
            return json.dumps(self._service.save_ui_state(data), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def browseFolder(self):
        """打开系统目录选择框（GUI 线程），返回选中路径或空串"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            path = QFileDialog.getExistingDirectory(None, "选择文档目录", "")
            return path or ""
        except Exception as e:
            print(f"[RagBridge] 目录选择失败: {e}")
            return ""

    # ================================================================
    # 导入控制
    # ================================================================

    @pyqtSlot(str, result=str)
    def startImport(self, options_json):
        """解析前端 JSON 为 ImportOptions 并启动后台导入"""
        try:
            data = json.loads(options_json or "{}")
        except Exception:
            data = {}
        options = self._options_from(data)
        result = self._service.start_import(options)
        return json.dumps(result, ensure_ascii=False)

    @pyqtSlot()
    def stopImport(self):
        self._service.stop_import()

    def _options_from(self, data: dict) -> ImportOptions:
        opts = self._service.default_options()
        if not isinstance(data, dict):
            return opts
        for k in ("root_dir", "collection", "database", "split_mode"):
            if data.get(k) is not None:
                setattr(opts, k, str(data[k]).strip())
        for k in ("file_extensions", "exclude_patterns"):
            if isinstance(data.get(k), list):
                setattr(opts, k, [str(x) for x in data[k] if str(x).strip()])
        for k in ("skip_existing", "detect_changes", "force_reprocess", "enable_code_structure"):
            if data.get(k) is not None:
                setattr(opts, k, bool(data[k]))
        for k in ("batch_size", "max_file_size_mb"):
            if data.get(k) is not None:
                try:
                    setattr(opts, k, int(data[k]))
                except (TypeError, ValueError):
                    pass
        return opts

    # ================================================================
    # 文件记录
    # ================================================================

    @pyqtSlot(str, result=str)
    def getRecords(self, filter_json):
        try:
            f = json.loads(filter_json or "{}")
        except Exception:
            f = {}
        try:
            result = self._service.get_records(
                search=f.get("search", ""),
                status=f.get("status", "") or None,
                page=int(f.get("page", 1) or 1),
                page_size=int(f.get("page_size", 50) or 50),
                database=f.get("database") or None,
                collection=f.get("collection") or None,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def exportCsv(self):
        """打开保存对话框导出记录 CSV"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            default_path = os.path.join(os.path.expanduser("~"), "rag_records.csv")
            path, _ = QFileDialog.getSaveFileName(None, "导出 CSV", default_path, "CSV 文件 (*.csv)")
            if not path:
                return json.dumps({"ok": False, "cancelled": True}, ensure_ascii=False)
            return json.dumps(self._service.export_csv(path), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def clearRecords(self):
        return json.dumps(self._service.clear_records(), ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def retryFile(self, file_path):
        return json.dumps(self._service.retry_file(file_path or ""), ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def deleteRecord(self, file_path):
        """删除单个文件的处理记录 + 对应向量数据"""
        try:
            return json.dumps(self._service.delete_file(file_path or ""), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, str, result=str)
    def deleteCollection(self, collection, database):
        """删除集合（向量数据 + 该库下该集合的记录）"""
        try:
            return json.dumps(self._service.delete_collection(collection or "", database or ""),
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def deleteDatabase(self, database):
        """删除向量数据库（全部集合 + 全部记录）"""
        try:
            return json.dumps(self._service.delete_database(database or ""), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    # ================================================================
    # 检索预览 / 模型下载
    # ================================================================

    @pyqtSlot(str, result=str)
    def testSearch(self, query_json):
        """后台线程检索 → 推 searchPreview 回调（检索阻塞数秒，不能在 GUI 线程）"""
        try:
            q = json.loads(query_json or "{}")
        except Exception:
            q = {}
        query = str(q.get("query") or "").strip()
        if not query:
            return json.dumps({"ok": False, "message": "请输入检索问题"}, ensure_ascii=False)
        top_k = int(q.get("top_k", 5) or 5)
        collection = q.get("collection") or None
        database = q.get("database") or None
        enable_rerank = bool(q.get("enable_rerank", True))

        def _run():
            try:
                payload = self._service.search_preview(
                    query, top_k=top_k, collection=collection, database=database,
                    enable_rerank=enable_rerank)
                payload["ok"] = True
            except Exception as e:
                payload = {"ok": False, "message": str(e)[:200]}
            self.execute_js("window.ragApp&&window.ragApp.searchPreview&&"
                            "window.ragApp.searchPreview(%s);"
                            % json.dumps(payload, ensure_ascii=False))
        threading.Thread(target=_run, daemon=True, name="rag-search").start()
        return json.dumps({"ok": True, "started": True}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def downloadModels(self):
        """后台线程补下载 embedding + rerank 模型（幂等），进度推进日志"""
        def _on_progress(msg):
            self._push_log(msg)
        try:
            return json.dumps(self._service.download_models(on_progress=_on_progress),
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)
