"""
MCP 数据库连接管理
独立的 mcp.db 用于存储 MCP 市场数据
"""
import os
import sqlite3
from typing import Optional


class MCPDatabase:
    """mcp.db 数据库管理器（单例）"""

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
        self._init_table()

    def _get_db_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_dir = os.path.join(base, "data", "database")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "mcp.db")

    def connect(self) -> sqlite3.Connection:
        import threading
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def disconnect(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()

    def _init_table(self):
        """初始化 mcp_market 表"""
        conn = self.connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_market (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT,
                github_repo_url TEXT,
                logo TEXT,
                description TEXT,
                author TEXT,
                issue_number INTEGER,
                installed INTEGER DEFAULT 0,
                tested INTEGER DEFAULT 0,
                server_type TEXT,
                labels TEXT,
                created_at TEXT,
                raw_issue TEXT,
                fetched_at TEXT
            )
        """)
        conn.commit()