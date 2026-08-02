"""
事务管理器 — 提供上下文管理器语法，异常自动回滚

用法:
    with db.transaction() as conn:
        conn.execute("INSERT INTO ...")
        conn.execute("UPDATE ...")
    # 正常退出自动 COMMIT，异常自动 ROLLBACK
"""
import sqlite3
from typing import Optional


class TransactionManager:
    """事务管理器

    每次事务使用独立连接：
    - __enter__: 创建新连接，开启事务
    - __exit__: 无异常则 COMMIT，有异常则 ROLLBACK，最后关闭连接
    """

    def __init__(self, db):
        """初始化事务管理器

        参数:
            db: 数据库实例（需有 _create_connection 或 connect 方法创建新连接）
        """
        self._db = db
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Connection:
        """进入事务：创建独立连接并开启事务"""
        if hasattr(self._db, "_create_connection"):
            self._conn = self._db._create_connection()
        else:
            self._conn = self._db.connect()
        self._conn.execute("BEGIN")
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出事务：正常则提交，异常则回滚，最后关闭连接"""
        if self._conn:
            try:
                if exc_type:
                    self._conn.rollback()
                else:
                    self._conn.commit()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
            finally:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
        return False  # 不吞异常