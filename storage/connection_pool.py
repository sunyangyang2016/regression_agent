"""
连接池 — 多线程并发访问 SQLite 的连接复用管理

使用 Queue 实现固定容量连接池：
- acquire(): 获取连接（带超时，池空可创建新连接）
- release(): 归还连接（自动回滚未完成事务）
- _is_valid(): 连接有效性检查
"""
import sqlite3
import threading
from queue import Queue, Empty
from typing import Optional


class ConnectionPool:
    """SQLite 连接池

    参数:
        db_path: 数据库文件路径
        max_size: 连接池最大容量（默认 10）
        min_size: 初始最小连接数（默认 2）
        timeout: 获取连接超时秒数（默认 10）
    """

    def __init__(self, db_path: str, max_size: int = 10, min_size: int = 2, timeout: int = 10):
        self._db_path = db_path
        self._max_size = max_size
        self._min_size = min_size
        self._timeout = timeout
        self._pool: Queue = Queue(maxsize=max_size)
        self._lock = threading.RLock()
        self._created = 0  # 已创建的连接总数（用于控制不超过 max_size）

        # 创建初始连接
        for _ in range(min_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
                self._created += 1

    # ==========================================
    # 内部方法
    # ==========================================

    def _create_connection(self) -> Optional[sqlite3.Connection]:
        """创建新连接并配置 PRAGMA"""
        try:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=self._timeout)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except Exception as e:
            print(f"[ConnectionPool] 创建连接失败: {e}")
            return None

    def _is_valid(self, conn: sqlite3.Connection) -> bool:
        """检查连接是否有效"""
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    # ==========================================
    # 公共方法
    # ==========================================

    def acquire(self, timeout: Optional[int] = None) -> sqlite3.Connection:
        """获取一个连接

        1. 从池中获取；2. 池空则创建新连接；3. 检查有效性；4. 无效则重建。
        """
        timeout = timeout or self._timeout
        try:
            conn = self._pool.get(timeout=timeout)
            if self._is_valid(conn):
                return conn
            # 连接失效，关闭并重建
            try:
                conn.close()
            except Exception:
                pass
            new_conn = self._create_connection()
            if new_conn:
                return new_conn
            # 重建失败，递归尝试
            return self.acquire(timeout)
        except Empty:
            # 池空，尝试创建新连接（不超过 max_size）
            with self._lock:
                if self._created < self._max_size:
                    new_conn = self._create_connection()
                    if new_conn:
                        self._created += 1
                        return new_conn
            raise TimeoutError(f"获取连接超时（{timeout}s），连接池已满")

    def release(self, conn: Optional[sqlite3.Connection]):
        """归还连接到连接池

        1. 检查有效性；2. 回滚未完成事务；3. 放入池中；4. 池满则关闭。
        """
        if not conn:
            return

        # 回滚未完成事务
        try:
            if conn.in_transaction:
                conn.rollback()
        except Exception:
            pass

        with self._lock:
            if self._pool.qsize() < self._max_size and self._is_valid(conn):
                self._pool.put(conn)
            else:
                try:
                    conn.close()
                    self._created -= 1
                except Exception:
                    pass

    def close_all(self):
        """关闭连接池中所有连接"""
        with self._lock:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                    self._created -= 1
                except Exception:
                    pass

    @property
    def size(self) -> int:
        """当前池中可用连接数"""
        return self._pool.qsize()