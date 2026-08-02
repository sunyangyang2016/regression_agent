"""
数据库迁移脚本 — 基于数据库 schema 版本号（PRAGMA user_version）执行迁移

用法:
    python scripts/migrate_db.py            # 查看当前状态
    python scripts/migrate_db.py --migrate  # 执行迁移

迁移机制:
    - 使用 SQLite 的 PRAGMA user_version 记录数据库 schema 版本
    - 每个版本号对应一次迁移逻辑
    - 按顺序执行未应用的迁移，避免重复迁移

版本对照（软件版本 → 数据库 schema 版本）:
    v1.0.1alpha 及以前（旧版）: schema_version = 0（无版本标记）
    v1.0.2alpha（新数据库存储）: schema_version = 1
    v1.0.3alpha（会话日志文件持久化）: schema_version = 2
"""
import json
import os
import sqlite3
import sys

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "user_config", "database")
AGENT_DB = os.path.join(DB_DIR, "agent.db")
LEGACY_MCP_DB = os.path.join(DB_DIR, "mcp.db")

# 当前数据库 schema 版本（与软件版本对应）
CURRENT_SCHEMA_VERSION = 2

# 迁移注册表: {目标版本: (描述, 迁移函数)}
MIGRATIONS = {}


def register_migration(version, description):
    """注册迁移函数装饰器"""
    def decorator(func):
        MIGRATIONS[version] = (description, func)
        return func
    return decorator


# ==========================================
# 迁移函数（按版本顺序）
# ==========================================

@register_migration(2, "为 history_sessions_index 表添加 log_file 列（AI 通信日志文件路径）")
def migrate_v2(conn: sqlite3.Connection):
    """schema v2: 为会话索引表添加 log_file 列，存储 AI 通信日志 JSON 文件路径"""
    # 注意：main() 中连接未设置 row_factory，PRAGMA 返回元组，用 [1] 取列名
    columns = [r[1] for r in conn.execute("PRAGMA table_info(history_sessions_index)").fetchall()]
    if "log_file" not in columns:
        conn.execute("ALTER TABLE history_sessions_index ADD COLUMN log_file TEXT")
        print("  [迁移 v2] history_sessions_index 已添加 log_file 列")
    else:
        print("  [迁移 v2] history_sessions_index 已存在 log_file 列，跳过")
    conn.execute("PRAGMA user_version = 2")


@register_migration(1, "创建 4 张数据表 + 从旧版 mcp.db 迁移市场数据")
def migrate_v1(conn: sqlite3.Connection):
    """schema v1: 初始化新数据库结构"""
    # 1. 创建 4 张数据表
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS history_sessions_index (
            id            TEXT PRIMARY KEY,
            title         TEXT,
            model         TEXT,
            message_count INTEGER DEFAULT 0,
            token_count   INTEGER DEFAULT 0,
            status        TEXT DEFAULT 'active',
            created_at    TEXT,
            updated_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_hsi_status ON history_sessions_index (status);
        CREATE INDEX IF NOT EXISTS idx_hsi_created ON history_sessions_index (created_at);

        CREATE TABLE IF NOT EXISTS history_sessions_messages (
            id            TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            role          TEXT NOT NULL,
            content       TEXT,
            tool_calls    TEXT,
            token_count   INTEGER DEFAULT 0,
            created_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_hsmsg_session ON history_sessions_messages (session_id);
        CREATE INDEX IF NOT EXISTS idx_hsmsg_created ON history_sessions_messages (created_at);

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
            fetched_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mmkt_name ON mcp_market_index (name);
        CREATE INDEX IF NOT EXISTS idx_mmkt_installed ON mcp_market_index (installed);
        CREATE INDEX IF NOT EXISTS idx_mmkt_server_type ON mcp_market_index (server_type);

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
            created_at  TEXT,
            updated_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mslog_server ON mcp_server_logs (server_id);
        CREATE INDEX IF NOT EXISTS idx_mslog_action ON mcp_server_logs (action);
        CREATE INDEX IF NOT EXISTS idx_mslog_created ON mcp_server_logs (created_at);
    """)

    # 2. 从旧版 mcp.db 迁移市场数据（如果存在）
    migrated = _migrate_legacy_mcp_market(conn)
    if migrated > 0:
        print(f"  [迁移 v1] 从旧版 mcp.db 迁移 {migrated} 条市场数据")
    else:
        print("  [迁移 v1] 无旧版 mcp.db 数据需要迁移（或已迁移）")

    conn.execute(f"PRAGMA user_version = 1")


def _migrate_legacy_mcp_market(conn: sqlite3.Connection) -> int:
    """从旧版 mcp.db 的 mcp_market 表迁移数据到 agent.db 的 mcp_market_index 表"""
    if not os.path.exists(LEGACY_MCP_DB):
        return 0

    try:
        legacy_conn = sqlite3.connect(LEGACY_MCP_DB)
        legacy_conn.row_factory = sqlite3.Row

        # 检查旧表是否存在
        tables = legacy_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_market'"
        ).fetchall()
        if not tables:
            legacy_conn.close()
            return 0

        rows = legacy_conn.execute("SELECT * FROM mcp_market").fetchall()
        legacy_conn.close()

        if not rows:
            return 0

        # 迁移数据（按 id 去重）
        migrated = 0
        for row in rows:
            d = dict(row)
            item_id = d.get("id")
            if not item_id:
                continue

            # 检查是否已存在
            exists = conn.execute(
                "SELECT COUNT(*) FROM mcp_market_index WHERE id = ?", (item_id,)
            ).fetchone()[0]
            if exists:
                continue

            # 映射字段（snake_case → snake_case）
            columns = [
                "id", "name", "title", "github_repo_url", "logo", "description",
                "author", "issue_number", "installed", "tested", "server_type",
                "labels", "created_at", "raw_issue", "fetched_at",
            ]
            values = []
            for col in columns:
                values.append(d.get(col))

            try:
                conn.execute(
                    f"INSERT INTO mcp_market_index "
                    f"({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))})",
                    tuple(values),
                )
                migrated += 1
            except Exception:
                continue

        return migrated

    except Exception as e:
        print(f"  [迁移 v1] 旧 mcp.db 读取失败（可忽略）: {e}")
        return 0


# ==========================================
# 主逻辑
# ==========================================

def get_current_version(conn: sqlite3.Connection) -> int:
    """获取当前数据库 schema 版本"""
    return conn.execute("PRAGMA user_version").fetchone()[0]


def run_migrations(conn: sqlite3.Connection):
    """按版本顺序执行所有未应用的迁移"""
    current = get_current_version(conn)
    print(f"当前数据库 schema 版本: {current}")
    print(f"目标 schema 版本: {CURRENT_SCHEMA_VERSION}")

    if current >= CURRENT_SCHEMA_VERSION:
        print("数据库已是最新版本，无需迁移")
        return False

    pending = sorted(
        [v for v in MIGRATIONS if v > current]
    )
    if not pending:
        print("没有待执行的迁移")
        return False

    for version in pending:
        desc, func = MIGRATIONS[version]
        print(f"\n执行迁移 -> v{version}: {desc}")
        try:
            # 每个迁移独立事务
            # 注意：migrate_v1 内部使用 executescript() 会隐式提交挂起事务，
            #       因此迁移函数完后需用 in_transaction 判断是否仍有活动事务。
            conn.execute("BEGIN")
            func(conn)
            if conn.in_transaction:
                conn.execute("COMMIT")
            else:
                print(f"  [提示] v{version} 内部已隐式提交事务（executescript）")
            print(f"  [完成] schema v{version}")
        except Exception as e:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            print(f"  [失败] schema v{version}: {e}")
            raise

    return True


def check_status():
    """查看当前数据库状态（不执行迁移）"""
    print(f"数据库文件: {AGENT_DB}")
    print(f"旧版数据库: {LEGACY_MCP_DB}")
    print()

    if not os.path.exists(AGENT_DB):
        print("状态: agent.db 不存在（首次运行将由应用自动创建）")
        return

    conn = sqlite3.connect(AGENT_DB)
    current = get_current_version(conn)

    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]

    print(f"当前 schema 版本: {current}")
    print(f"数据表: {tables}")

    # 市场数据计数
    if "mcp_market_index" in tables:
        count = conn.execute("SELECT COUNT(*) FROM mcp_market_index").fetchone()[0]
        print(f"mcp_market_index 数据量: {count}")

    if current < CURRENT_SCHEMA_VERSION:
        print("\n提示: 有可用的数据库迁移，执行: python scripts/migrate_db.py --migrate")
    else:
        print("\n状态: 数据库已是最新版本")

    if os.path.exists(LEGACY_MCP_DB):
        print("提示: 检测到旧版 mcp.db（将被迁移/废弃）")

    conn.close()


def main():
    args = sys.argv[1:]
    do_migrate = "--migrate" in args

    if not do_migrate:
        check_status()
        return

    # 执行迁移
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(AGENT_DB)

    print("=" * 50)
    print("数据库迁移开始")
    print("=" * 50)
    print()

    try:
        changed = run_migrations(conn)
        if changed:
            print("\n数据库迁移完成")
        else:
            print("\n无需迁移")
    except Exception as e:
        print(f"\n迁移失败: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()