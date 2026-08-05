"""
统一数据库入口 — agent.db（单例）

负责:
- 管理数据库连接（WAL、连接池、SQL 执行）
- 启动时确保 4 张数据表存在（幂等建表，原生 SQL，不做数据迁移）

数据迁移由 scripts/migrate_db.py 根据 schema 版本号（PRAGMA user_version）手动执行。
"""
from typing import List

from storage.base_db import BaseDatabase


class Database(BaseDatabase):
    """agent.db 数据库管理器（单例）"""

    _instance = None
    _db_filename = "agent.db"

    # 4 张数据表名（供 ensure_tables / 状态检查使用）
    TABLES = [
        "history_sessions_index",
        "history_sessions_messages",
        "mcp_market_index",
        "mcp_server_logs",
    ]

    # 建表 SQL（幂等 CREATE TABLE IF NOT EXISTS + 索引）
    TABLE_DDL = [
        """
        CREATE TABLE IF NOT EXISTS history_sessions_index (
            id                TEXT PRIMARY KEY,
            title             TEXT,
            model             TEXT,
            message_count     INTEGER DEFAULT 0,
            token_count       INTEGER DEFAULT 0,
            hit_token_count   INTEGER DEFAULT 0,
            miss_token_count  INTEGER DEFAULT 0,
            output_token_count INTEGER DEFAULT 0,
            status            TEXT DEFAULT 'active',
            created_at        TEXT,
            updated_at        TEXT,
            log_file          TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS history_sessions_messages (
            id            TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            role          TEXT NOT NULL,
            content       TEXT,
            tool_calls    TEXT,
            token_count   INTEGER DEFAULT 0,
            round_no      INTEGER,
            marker        TEXT,
            created_at    TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mcp_market_index (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            title           TEXT,
            github_repo_url TEXT,
            logo            TEXT,
            description     TEXT,
            author          TEXT,
            issue_number    INTEGER,
            installed       INTEGER DEFAULT 0,
            tested          INTEGER DEFAULT 0,
            server_type     TEXT,
            labels          TEXT,
            created_at      TEXT,
            raw_issue       TEXT,
            fetched_at      TEXT,
            server_id       TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mcp_server_logs (
            id          TEXT PRIMARY KEY,
            server_id   TEXT NOT NULL,
            action      TEXT,
            status      TEXT,
            log_content TEXT,
            log_file    TEXT,
            duration    REAL,
            server_name TEXT,
            repo_url    TEXT,
            market_id   TEXT,
            created_at  TEXT,
            updated_at  TEXT
        )
        """,
    ]

    # 索引 SQL（幂等）
    INDEX_DDL = [
        "CREATE INDEX IF NOT EXISTS idx_hsi_status ON history_sessions_index (status)",
        "CREATE INDEX IF NOT EXISTS idx_hsi_created ON history_sessions_index (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_hsmsg_session ON history_sessions_messages (session_id)",
        "CREATE INDEX IF NOT EXISTS idx_hsmsg_created ON history_sessions_messages (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_mmkt_name ON mcp_market_index (name)",
        "CREATE INDEX IF NOT EXISTS idx_mmkt_installed ON mcp_market_index (installed)",
        "CREATE INDEX IF NOT EXISTS idx_mmkt_server_type ON mcp_market_index (server_type)",
        "CREATE INDEX IF NOT EXISTS idx_mslog_server ON mcp_server_logs (server_id)",
        "CREATE INDEX IF NOT EXISTS idx_mslog_action ON mcp_server_logs (action)",
        "CREATE INDEX IF NOT EXISTS idx_mslog_created ON mcp_server_logs (created_at)",
    ]

    def __init__(self):
        super().__init__()
        # 启动时确保 4 张数据表存在（幂等建表，不做数据迁移）
        self.ensure_tables()

    def ensure_tables(self):
        """确保 4 张数据表存在（CREATE TABLE IF NOT EXISTS + 索引，幂等）

        - 全新环境：自动创建 4 张空表 + 索引
        - 正常启动：表已存在则跳过，零副作用
        - 部分缺失：自动补建缺失的表

        注意：只建表结构，不导入任何数据（迁移由 migrate_db.py 手动执行）
        """
        try:
            for ddl in self.TABLE_DDL:
                self.execute(ddl)
            for idx in self.INDEX_DDL:
                self.execute(idx)
        except Exception as e:
            print(f"[Database] 建表失败: {e}")

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        result = self.query_value(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return bool(result)

    def table_names(self) -> List[str]:
        """获取当前数据库中所有表名"""
        rows = self.query("SELECT name FROM sqlite_master WHERE type='table'")
        return [r["name"] for r in rows]

    # ==========================================
    # 事务
    # ==========================================

    def transaction(self):
        """创建事务管理器（上下文管理器用法）"""
        from storage.transaction import TransactionManager
        return TransactionManager(self)