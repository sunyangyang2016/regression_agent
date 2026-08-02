"""
数据库连接基类 — 统一单例模式 + 连接池管理 + WAL 并发支持

所有具体数据库继承此类，只需指定 `_db_filename`，
自动获得统一的路径计算、连接池管理、单例模式、SQL 执行等公共逻辑。

核心特性：
- 连接池多连接：每个 SQL 操作获取独立连接，用完归还，支持多线程并发（事务互不干扰）
- WAL 模式 + busy_timeout：读写并发友好
- 线程安全：连接池内部使用 Queue + RLock

注意: 建表与数据迁移不由数据库类自动执行，
统一由 scripts/migrate_db.py 根据 schema 版本号（PRAGMA user_version）负责。
"""
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Union

from storage.connection_pool import ConnectionPool


class BaseDatabase:
    """数据库抽象基类

    子类需指定 `_db_filename`（如 "agent.db"）。
    使用连接池管理多连接，支持多线程并发访问。
    """

    _instance = None
    _db_filename = ""  # 子类指定数据库文件名

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._lock = threading.RLock()
        self._db_path: str = self._get_db_path()
        # ★ 连接池（多连接，支持多线程并发）
        self._pool = ConnectionPool(self._db_path, max_size=10, min_size=2)
        # 自动调用建表钩子（子类覆盖 _init_tables 实现具体建表）
        self._init_tables()

    # ==========================================
    # 路径管理
    # ==========================================

    @property
    def db_path(self) -> str:
        """数据库文件完整路径"""
        return self._db_path

    def _get_db_path(self) -> str:
        """统一数据库目录：user_config/database/{_db_filename}"""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_dir = os.path.join(base, "user_config", "database")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, self._db_filename)

    # ==========================================
    # 连接管理（连接池）
    # ==========================================

    def _acquire(self) -> sqlite3.Connection:
        """从连接池获取一个独立连接（内部使用，用完须 _release）"""
        return self._pool.acquire()

    def _release(self, conn: Optional[sqlite3.Connection]):
        """归还连接到连接池（内部使用）"""
        self._pool.release(conn)

    def connect(self) -> sqlite3.Connection:
        """获取一个连接（兼容入口）

        注意：调用方持有期间请勿跨线程共享；
        用完建议调用 `release_conn(conn)` 归还，或使用内部方法（自动归还）。
        """
        return self._pool.acquire()

    def release_conn(self, conn: Optional[sqlite3.Connection]):
        """手动归还连接（配合 connect() 使用）"""
        self._pool.release(conn)

    def disconnect(self):
        """关闭连接池中所有连接"""
        with self._lock:
            self._pool.close_all()

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的独立连接（供事务等场景使用，需调用方自行关闭）

        配置 PRAGMA 参数，与连接池一致。
        """
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        """获取一个连接（兼容入口，等同 connect()）"""
        return self.connect()

    # ==========================================
    # SQL 执行（获取→执行→归还，线程安全）
    # ==========================================

    def execute(self, sql: str, params: tuple = ()) -> int:
        """执行写操作（INSERT/UPDATE/DELETE），返回影响行数"""
        conn = self._acquire()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._release(conn)

    def executemany(self, sql: str, params_list: List[tuple]) -> int:
        """批量执行写操作，返回影响行数"""
        conn = self._acquire()
        try:
            cursor = conn.executemany(sql, params_list)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._release(conn)

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行查询，返回字典列表"""
        conn = self._acquire()
        try:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._release(conn)

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """执行查询，返回单条字典"""
        conn = self._acquire()
        try:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            self._release(conn)

    def query_value(self, sql: str, params: tuple = ()):
        """执行查询，返回单个值（如 COUNT(*)）"""
        conn = self._acquire()
        try:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            self._release(conn)

    # ==========================================
    # 建表钩子（子类可覆盖）
    # ==========================================

    def _init_tables(self):
        """初始化数据表 — 子类覆盖此方法实现具体建表逻辑"""
        pass