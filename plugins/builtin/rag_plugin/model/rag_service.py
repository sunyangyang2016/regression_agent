"""RAG 插件模型层（MVC Model）— 导入 / 记录 / 统计 / 检索预览 的薄封装

依赖纯逻辑库 rag/（headless，可独立测试），本层不 import Qt；
后台线程与回调推送（execute_js）由 bridge 层接线。
"""
import dataclasses
import logging
import os
import threading

from rag_mcp_server.config_manager import get_config_manager
from rag_mcp_server.file_tracker import FileTracker
from rag_mcp_server.import_engine import ImportEngine
from rag_mcp_server.models import ImportOptions

logger = logging.getLogger(__name__)
from rag_mcp_server.vector_store_manager import VectorStoreManager


class RagService:
    """RAG 知识库业务模型：导入、文件记录、统计、检索预览"""

    def __init__(self, config=None, on_progress=None, on_log=None,
                 on_done=None, on_records_changed=None):
        self._config = config or get_config_manager()
        self._on_progress = on_progress          # cb(done:int, total:int)
        self._on_log = on_log                    # cb(msg:str)
        self._on_done = on_done                  # cb(stats:dict)
        self._on_records_changed = on_records_changed   # cb() 每文件完成
        self._cancel_event = None
        self._worker = None
        self._engine = ImportEngine(config=self._config)

    # ================================================================
    # 导入
    # ================================================================
    def start_import(self, options: ImportOptions) -> dict:
        """后台线程执行 ImportEngine.run；立即返回，结果经 on_done 回调"""
        if self.is_importing():
            return {"ok": False, "message": "已有导入任务正在进行"}
        if not options.root_dir or not os.path.isdir(options.root_dir):
            return {"ok": False, "message": "请先选择有效的文档目录"}
        if not (options.collection or "").strip():
            return {"ok": False, "message": "请填写集合名称"}

        self._cancel_event = threading.Event()
        self._emit_log("▶ 开始导入 → %s" % options.root_dir)

        def _run():
            try:
                stats = self._engine.run(
                    options,
                    cancel_event=self._cancel_event,
                    progress_cb=self._on_progress,
                    file_done_cb=lambda path, status, message: self._emit_records_changed(),
                    log_cb=self._on_log,
                )
            except Exception as e:
                from rag_mcp_server.models import ImportStats
                self._emit_log("❌ 导入异常: %s" % e)
                stats = ImportStats(error_messages=[str(e)])
            self._notify_done(stats)

        self._worker = threading.Thread(target=_run, daemon=True, name="rag-import")
        self._worker.start()
        return {"ok": True, "started": True}

    def stop_import(self):
        """请求停止（处理完当前文件后中断）"""
        if self._cancel_event:
            self._cancel_event.set()
            self._emit_log("⚠ 正在停止…（处理完当前文件后停止）")

    def is_importing(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    # ================================================================
    # 文件记录
    # ================================================================
    def get_records(self, search: str = "", status: str = "",
                    page: int = 1, page_size: int = 50,
                    database: str = None, collection: str = None) -> dict:
        tracker = FileTracker(config=self._config)
        page = max(1, int(page or 1))
        page_size = min(200, max(1, int(page_size or 50)))
        rows, total = tracker.query_records(
            search=search or "", status=status or None,
            database=(database or "").strip() or None,
            collection=(collection or "").strip() or None,
            page=page, page_size=page_size)
        return {"rows": rows, "total": total, "page": page, "page_size": page_size,
                "database": database, "collection": collection}

    def export_csv(self, path: str) -> dict:
        tracker = FileTracker(config=self._config)
        try:
            n = tracker.export_csv(path)
            return {"ok": True, "count": n, "path": path}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def clear_records(self) -> dict:
        """清空全部文件处理记录 + 删除全部向量库数据（所有集合）"""
        tracker = FileTracker(config=self._config)
        store = VectorStoreManager(config=self._config)
        try:
            n = tracker.clear()
            cols = store.clear_all_collections()
            return {"ok": True, "count": n, "collections_deleted": cols}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def retry_file(self, file_path: str) -> dict:
        """重试单个文件：以文件所在目录为根，已成功的文件自动跳过"""
        if not file_path or not os.path.exists(file_path):
            return {"ok": False, "message": "文件不存在"}
        options = self.default_options()
        options.root_dir = os.path.dirname(file_path)
        options.force_reprocess = False
        options.skip_existing = True
        options.detect_changes = False
        return self.start_import(options)

    def delete_file(self, file_path: str) -> dict:
        """删除单个文件的处理记录 + 对应向量数据（块）"""
        if not (file_path or "").strip():
            return {"ok": False, "message": "缺少文件路径"}
        tracker = FileTracker(config=self._config)
        store = VectorStoreManager(config=self._config)
        rec = tracker.get_record(file_path)
        try:
            tracker.delete_record(file_path)
        except Exception as e:
            return {"ok": False, "message": str(e)}
        deleted_chunks = 0
        if rec:
            db = rec.get("database") or self._config.current_database
            coll = rec.get("collection_name")
            if coll:
                try:
                    deleted_chunks = store.delete_file(coll, file_path, database=db)
                except Exception as e:
                    logger.warning("删除向量数据失败 %s: %s", file_path, e)
        return {"ok": True, "deleted_chunks": deleted_chunks}

    def delete_collection(self, collection: str, database: str = None) -> dict:
        """删除集合：向量数据 + 该库下该集合的全部文件记录"""
        collection = (collection or "").strip()
        if not collection:
            return {"ok": False, "message": "请输入集合名称"}
        db = (database or "").strip() or self._config.current_database
        store = VectorStoreManager(config=self._config)
        try:
            store.delete_collection(collection, database=db)
        except Exception as e:
            return {"ok": False, "message": str(e)}
        tracker = FileTracker(config=self._config)
        try:
            n = tracker.delete_records(database=db, collection=collection)
        except Exception as e:
            n = 0
            logger.warning("删除集合 %s/%s 记录失败: %s", db, collection, e)
        return {"ok": True, "records_deleted": n}

    def delete_database(self, database: str = None) -> dict:
        """删除数据库：全部集合 + 该库全部文件记录"""
        db = (database or "").strip()
        if not db:
            return {"ok": False, "message": "请输入向量数据库名称"}
        store = VectorStoreManager(config=self._config)
        try:
            cols = store.delete_database(db)
        except Exception as e:
            return {"ok": False, "message": str(e)}
        tracker = FileTracker(config=self._config)
        try:
            n = tracker.delete_records(database=db)
        except Exception as e:
            n = 0
            logger.warning("删除数据库 %s 记录失败: %s", db, e)
        # 删除的是当前库 → 重置回 default
        if db == self._config.current_database:
            self._config.set_current_database("default")
        return {"ok": True, "collections_deleted": cols, "records_deleted": n}

    # ================================================================
    # 状态 / 统计
    # ================================================================
    def get_light_status(self) -> dict:
        """轻量状态（GUI 线程同步可承受）：运行中 + 模型就绪 + 记录计数"""
        from rag_mcp_server.model_manager import get_model_manager
        mm = get_model_manager(self._config)
        tracker = FileTracker(config=self._config)
        try:
            counts = tracker.counts()
        except Exception:
            counts = {}
        return {
            "running": self.is_importing(),
            "counts": counts,
            "model_ready": {
                "embedding": mm.is_model_ready("embedding"),
                "rerank": mm.is_model_ready("rerank"),
            },
        }

    def refresh_stats(self, database: str = None, collection: str = None) -> dict:
        """较重统计（ChromaDB 目录扫描 + 集合计数），应放后台线程调用

        database 限定统计哪个向量库；collection 限定「已处理」记录计数到某个集合
        （为空则统计该库全部集合）。向量块总数是整库级，前端按当前集合换算。
        """
        store = VectorStoreManager(config=self._config)
        tracker = FileTracker(config=self._config)
        db = (database or "").strip() or self._config.current_database
        databases = []
        try:
            databases = store.list_databases()
        except Exception as e:
            logger.warning("列出向量数据库失败: %s", e)
        try:
            stats = store.stats(database=db)
        except Exception as e:
            stats = {"error": str(e)}
        try:
            counts = tracker.counts(database=db, collection=(collection or "").strip() or None)
        except Exception:
            counts = {}
        return {
            "counts": counts,
            "databases": databases,
            "current_database": db,
            "current_collection": collection or "",
            "collections": stats.get("collections", []),
            "per_collection": stats.get("per_collection", {}),
            "total_files": stats.get("total_files", 0),
            "total_chunks": stats.get("total_chunks", 0),
            "total_size_mb": stats.get("total_size_mb", 0.0),
            "file_types": stats.get("file_types", {}),
            "last_import": stats.get("last_import"),
        }

    # ================================================================
    # 向量数据库
    # ================================================================
    def set_database(self, name: str) -> dict:
        """持久化当前向量数据库选择"""
        try:
            self._config.set_current_database(name or "default")
            return {"ok": True, "database": self._config.current_database}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def list_databases(self) -> list:
        """列出全部向量数据库名"""
        try:
            return VectorStoreManager(config=self._config).list_databases()
        except Exception as e:
            logger.warning("列出向量数据库失败: %s", e)
            return []

    # ================================================================
    # 默认配置
    # ================================================================
    def default_options(self) -> ImportOptions:
        """默认导入参数：优先取 user 已保存的 UI 状态（ui.*），缺失回退功能配置。

        即 UI 表单的改动会持久化为后续导入（含 retry_file / 配置驱动的导入）的默认值。
        """
        c = self._config
        collection = (c.get("ui.default_collection") or "").strip() or \
            c.get("retrieval.default_collection", "knowledge") or "knowledge"
        database = (c.get("ui.database") or "").strip() or \
            c.get("chromadb.current_database", "default") or "default"
        root_dir = (c.get("ui.default_root_dir") or "").strip()
        split_mode = (c.get("ui.split_mode") or "").strip() or \
            c.get("chunking.split_mode", "smart") or "smart"
        file_extensions = c.get("ui.file_extensions")
        if isinstance(file_extensions, str):
            file_extensions = [e.strip() for e in file_extensions.split(",") if e.strip()]
        if not file_extensions:
            file_extensions = list(c.get("import.file_extensions", []) or [])
        return ImportOptions(
            root_dir=root_dir,
            collection=collection,
            database=database,
            file_extensions=file_extensions,
            skip_existing=bool(c.get("ui.skip_existing", c.get("import.skip_existing", True))),
            detect_changes=bool(c.get("ui.detect_changes", c.get("import.detect_changes", True))),
            force_reprocess=bool(c.get("import.force_reprocess", False)),
            split_mode=split_mode,
            batch_size=int(c.get("import.batch_size", 64) or 64),
            max_file_size_mb=int(c.get("import.max_file_size_mb", 100) or 100),
            exclude_patterns=list(c.get("import.exclude_patterns", []) or []),
            enable_code_structure=bool(c.get("ui.enable_code_structure", c.get("chunking.code.enabled", True))),
        )

    def defaults(self) -> dict:
        """前端表单预填的默认配置（ui.* 保存状态优先）"""
        opts = self.default_options()
        c = self._config
        # 现有向量数据库列表（快速，供前端下拉填充）
        databases = []
        try:
            databases = VectorStoreManager(config=self._config).list_databases()
        except Exception as e:
            logger.warning("列出向量数据库失败: %s", e)
        return {
            "root_dir": opts.root_dir,
            "collection": opts.collection,
            "database": opts.database,
            "current_collection": (c.get("ui.current_collection") or "").strip() or "",
            "databases": databases,
            "split_mode": opts.split_mode,
            "file_extensions": ",".join(opts.file_extensions or []),
            "exclude_patterns": opts.exclude_patterns,
            "skip_existing": opts.skip_existing,
            "detect_changes": opts.detect_changes,
            "force_reprocess": opts.force_reprocess,
            "enable_code_structure": opts.enable_code_structure,
            "max_file_size_mb": opts.max_file_size_mb,
            "batch_size": opts.batch_size,
            "split_modes": {
                "smart": "智能分段", "paragraph": "按段落",
                "heading": "按章节", "fixed": "按固定大小", "code": "代码结构化",
            },
        }

    def save_ui_state(self, data: dict) -> dict:
        """持久化 UI 表单状态到 user/rag_config.json（defaults/ 不被修改）"""
        try:
            self._config.save_ui_state(data or {})
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ================================================================
    # 检索预览
    # ================================================================
    def search_preview(self, query: str, top_k: int = 5, collection: str = None,
                       database: str = None, enable_rerank: bool = True) -> dict:
        from rag_mcp_server.rag_client import RAGClient
        client = RAGClient(config=self._config)
        result = client.retrieve(
            query, top_k=top_k, collection=collection, database=database,
            enable_rerank=enable_rerank, score_threshold=0.0)
        chunks = []
        for c in result.chunks:
            md = c.metadata or {}
            chunks.append({
                "content": c.content,
                "score": round(c.score, 4),
                "rough_score": round(c.rough_score, 4),
                "file_name": md.get("file_name", ""),
                "file_path": md.get("file_path", ""),
                "heading_path": md.get("heading_path", ""),
                "chunk_index": md.get("chunk_index", ""),
            })
        meta = result.metadata
        return {
            "query": query,
            "chunks": chunks,
            "count": len(chunks),
            "total_time_ms": meta.total_time_ms,
            "rough_count": meta.rough_count,
            "rerank_enabled": meta.rerank_enabled,
            "rerank_skipped": meta.rerank_skipped,
            "error": meta.error,
            "collection": meta.collection,
        }

    # ================================================================
    # 模型
    # ================================================================
    def is_model_ready(self, kind: str) -> bool:
        from rag_mcp_server.model_manager import get_model_manager
        return get_model_manager(self._config).is_model_ready(kind)

    def download_models(self, on_progress=None) -> dict:
        """后台线程补下载两个模型（幂等），返回是否启动下载"""
        from rag_mcp_server.model_manager import get_model_manager
        mm = get_model_manager(self._config)
        if mm.is_model_ready("embedding") and mm.is_model_ready("rerank"):
            return {"ok": True, "started": False, "message": "模型均已就绪，无需下载"}
        mm.download_models_async(progress=on_progress)
        return {"ok": True, "started": True, "message": "已开始后台下载模型，请查看日志"}

    # ================================================================
    # 内部
    # ================================================================
    def _emit_log(self, msg: str):
        if self._on_log:
            try:
                self._on_log(msg)
            except Exception:
                pass

    def _emit_records_changed(self):
        if self._on_records_changed:
            try:
                self._on_records_changed()
            except Exception:
                pass

    def _notify_done(self, stats):
        if not self._on_done:
            return
        try:
            payload = dataclasses.asdict(stats)
        except Exception:
            payload = {"error_messages": [str(stats)]}
        try:
            self._on_done(payload)
        except Exception:
            pass
