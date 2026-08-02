# 🗄️ 数据库目录

本目录存放 Agent 应用运行时生成的 **SQLite 数据库文件**。

## 目录内容

| 文件 | 说明 | 是否纳入版本库 |
|------|------|--------------|
| `agent.db` | 应用统一数据库（会话、消息、MCP 市场、日志） | ❌ 否（运行时生成） |
| `agent.db-shm` | SQLite WAL 模式的共享内存文件 | ❌ 否（临时文件） |
| `agent.db-wal` | SQLite WAL 模式的预写日志文件 | ❌ 否（临时文件） |
| `README.md` | 本说明文档 | ✅ 是 |

> 📌 数据库文件（`*.db`、`*.db-shm`、`*.db-wal`）均为程序运行时自动生成，包含本地会话等数据，**不纳入版本库**，也已通过 `.gitignore` 排除。

## 数据库设计

- **数据库文件**：`agent.db`（唯一数据库，SQLite + WAL 模式）
- **Schema 版本**：通过 `PRAGMA user_version` 管理
- **建表**：应用启动时由 `storage/database.py` 的 `ensure_tables()` 自动执行（幂等）

### 数据表（4 张）

| 表名 | 用途 |
|------|------|
| `history_sessions_index` | 历史会话索引（侧边栏列表） |
| `history_sessions_messages` | 历史会话消息明细 |
| `mcp_market_index` | MCP 市场安装目录 |
| `mcp_server_logs` | MCP 服务器操作日志 |

### 数据迁移

```bash
python scripts/migrate_db.py            # 查看当前状态
python scripts/migrate_db.py --migrate  # 执行迁移（建表 + 旧数据导入）
```

更多细节请参阅 [`docs/database_storage.md`](../../docs/database_storage.md)。