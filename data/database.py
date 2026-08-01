"""
数据库连接管理
"""
import os
import sqlite3
from typing import Optional


class Database:
    """SQLite 数据库管理器（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._conn: Optional[sqlite3.Connection] = None
        self._db_path: str = self._get_db_path()
    
    def _get_db_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_dir = os.path.join(base, "data", "database")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "agent.db")
    
    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def disconnect(self):
        if self._conn:
            self._conn.close()
            self._conn = None
    
    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()