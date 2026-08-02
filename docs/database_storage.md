# 📦 数据库存储设计文档

> 本文档描述 Agent 应用统一数据库存储方案，包含数据表结构、字段说明、表关系及数据库业务逻辑。

---

## 一、数据库概述

### 1.1 数据库文件

| 项目 | 说明 |
|------|------|
| **数据库文件** | `agent.db`（唯一数据库） |
| **文件路径** | `user_config/database/agent.db` |
| **旧版数据库** | `mcp.db`（已废弃，数据迁移至 `agent.db`） |

### 1.2 版本与迁移

数据库采用 **Schema 版本号（`PRAGMA user_version`）** 管理结构变更：

| 软件版本 | 数据库 Schema 版本 | 说明 |
|---------|-------------------|------|
| v1.0.1alpha 及以前 | 0（无版本标记） | 旧版（含 mcp.db） |
| v1.0.2alpha、v0.2.0 | 1 | 新版统一数据库（本方案） |
| v1.0.3alpha | 2 | 会话日志文件持久化（log_file 列） |
| v1.0.4alpha | 3 | 命中/未命中/输出 token 分栏统计 |

- **建表 = 启动时自动**：由 `storage/database.py` 的 `ensure_tables()` 执行（`CREATE TABLE IF NOT EXISTS` 幂等）
- **数据迁移 = 手动脚本**：由 `scripts/migrate_db.py` 根据 `PRAGMA user_version` 执行
- 每次软件版本升级时，在迁移脚本中注册新的迁移版本，按顺序执行
- 用法：`python scripts/migrate_db.py` 查看状态；`python scripts/migrate_db.py --migrate` 执行迁移

### 1.2 存储层目录结构

```
storage/
├── __init__.py
├── base_db.py                # 数据库连接基类（连接池）
├── database.py               # 统一 Database 入口（单例，原生 SQL 建表）
├── connection_pool.py        # 连接池
├── transaction.py            # 事务管理器
├── initializer.py            # 数据库初始化与状态检查
└── repositories/             # 仓库层（持有 db，原生 SQL）
    ├── __init__.py
    ├── conversation_repo.py      # 会话仓库
    ├── message_repo.py           # 消息仓库
    ├── mcp_market_repo.py        # MCP 市场仓库
    └── mcp_server_logs_repo.py   # MCP 服务器日志仓库
```

### 1.3 表总览（4 张表）

| 表名 | 角色 | 用途 |
|------|------|------|
| `history_sessions_index` | 📋 目录 | 历史会话索引（侧边栏列表） |
| `history_sessions_messages` | 📄 内容 | 历史会话消息明细 |
| `mcp_market_index` | 🛒 目录 | MCP 市场安装目录 |
| `mcp_server_logs` | 📝 日志 | MCP 服务器操作日志 |

---

## 二、数据表详细字段说明

### 2.1 `history_sessions_index` — 历史会话目录表

> 存储每个历史会话的元信息，对应 UI 侧边栏的对话列表。

**建表 SQL：**
```sql
CREATE TABLE IF NOT EXISTS history_sessions_index (
    id                TEXT PRIMARY KEY,             -- 会话 ID（UUID）
    title             TEXT,                         -- 会话标题
    model             TEXT,                         -- 使用的 AI 模型
    message_count     INTEGER DEFAULT 0,            -- 消息总数
    token_count       INTEGER DEFAULT 0,            -- Token 累计总数（= hit + miss + output）
    hit_token_count   INTEGER DEFAULT 0,            -- 命中缓存输入 token 累计
    miss_token_count  INTEGER DEFAULT 0,            -- 未命中缓存输入 token 累计
    output_token_count INTEGER DEFAULT 0,           -- 输出 token 累计
    status            TEXT DEFAULT 'active',        -- 状态：active / archived / deleted
    created_at        TEXT,                         -- 创建时间（ISO 8601）
    updated_at        TEXT                          -- 更新时间（ISO 8601）
);
```

**字段说明：**

| 字段 | 类型 | 主键 | 可空 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| `id` | TEXT | ✅ | ❌ | - | 会话唯一标识（UUID） |
| `title` | TEXT | - | ✅ | - | 会话标题，如"新对话"或首条消息摘要 |
| `model` | TEXT | - | ✅ | - | AI 模型名称（如 `deepseek-chat`） |
| `message_count` | INTEGER | - | ✅ | 0 | 该会话下的消息条数 |
| `token_count` | INTEGER | - | ✅ | 0 | 该会话累计消耗 Token 总数（= hit + miss + output） |
| `hit_token_count` | INTEGER | - | ✅ | 0 | 命中缓存输入 token 累计（`cached_tokens`） |
| `miss_token_count` | INTEGER | - | ✅ | 0 | 未命中缓存输入 token 累计（`prompt_tokens − cached_tokens`） |
| `output_token_count` | INTEGER | - | ✅ | 0 | 输出 token 累计（`completion_tokens`） |
| `status` | TEXT | - | ✅ | 'active' | 会话状态：`active`/`archived`/`deleted` |
| `created_at` | TEXT | - | ✅ | - | 创建时间 |
| `updated_at` | TEXT | - | ✅ | - | 最后更新时间 |

**索引：** `status`（按状态筛选会话）、`created_at`（按时间排序）

---

### 2.2 `history_sessions_messages` — 历史会话内容表

> 存储每个历史会话中的消息明细，与 `history_sessions_index` 为 1:N 关系。

**建表 SQL：**
```sql
CREATE TABLE IF NOT EXISTS history_sessions_messages (
    id            TEXT PRIMARY KEY,                 -- 消息 ID（UUID）
    session_id    TEXT NOT NULL,                    -- 所属会话 ID（外键 → history_sessions_index.id）
    role          TEXT NOT NULL,                    -- 角色：system / user / assistant / tool
    content       TEXT,                             -- 消息内容
    tool_calls    TEXT,                             -- 工具调用列表（JSON 数组）
    token_count   INTEGER DEFAULT 0,                -- 该消息 Token 数
    created_at    TEXT                              -- 创建时间（ISO 8601）
);
```

**字段说明：**

| 字段 | 类型 | 主键 | 可空 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| `id` | TEXT | ✅ | ❌ | - | 消息唯一标识（UUID） |
| `session_id` | TEXT | - | ❌ | - | 所属会话 ID，外键关联 `history_sessions_index.id` |
| `role` | TEXT | - | ❌ | - | 消息角色：`system`/`user`/`assistant`/`tool` |
| `content` | TEXT | - | ✅ | - | 消息正文内容 |
| `tool_calls` | TEXT | - | ✅ | - | 工具调用列表，JSON 数组（含名称、参数、结果） |
| `token_count` | INTEGER | - | ✅ | 0 | 该消息的 Token 消耗量 |
| `created_at` | TEXT | - | ✅ | - | 消息创建时间 |

**索引：** `session_id`（按会话快速查询消息）、`created_at`（按时间排序）

---

### 2.3 `mcp_market_index` — MCP 市场安装目录表

> 存储从 GitHub MCP Marketplace 抓取的服务器列表，对应前端市场卡片。

**建表 SQL：**
```sql
CREATE TABLE IF NOT EXISTS mcp_market_index (
    id              TEXT PRIMARY KEY,               -- 服务器 ID
    name            TEXT NOT NULL,                  -- 服务器名称
    title           TEXT,                           -- 显示标题
    github_repo_url TEXT,                           -- GitHub 仓库地址
    logo            TEXT,                           -- LOGO 图片 URL
    description     TEXT,                           -- 简介描述
    author          TEXT,                           -- 作者
    issue_number    INTEGER,                        -- GitHub Issue 编号
    installed       INTEGER DEFAULT 0,              -- 是否已安装 0/1
    tested          INTEGER DEFAULT 0,              -- 是否已验证 0/1
    server_type     TEXT,                           -- 类型：local / remote
    labels          TEXT,                           -- 标签列表（JSON 数组）
    created_at      TEXT,                           -- 市场条目创建时间
    raw_issue       TEXT,                           -- GitHub Issue 原始数据（JSON）
    fetched_at      TEXT                            -- 抓取时间
);
```

**字段说明：**

| 字段 | 类型 | 主键 | 可空 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| `id` | TEXT | ✅ | ❌ | - | 服务器唯一标识（如 `mcp-123`） |
| `name` | TEXT | - | ❌ | - | 服务器名称 |
| `title` | TEXT | - | ✅ | - | 显示标题（来自 Issue 标题） |
| `github_repo_url` | TEXT | - | ✅ | - | GitHub 仓库地址，安装时克隆来源 |
| `logo` | TEXT | - | ✅ | - | 服务器 LOGO 图片 URL |
| `description` | TEXT | - | ✅ | - | 简介描述（截取自 Issue） |
| `author` | TEXT | - | ✅ | - | 作者 GitHub 用户名 |
| `issue_number` | INTEGER | - | ✅ | - | 对应 GitHub Issue 编号 |
| `installed` | INTEGER | - | ✅ | 0 | 安装标记：`0` 未安装 / `1` 已安装 |
| `tested` | INTEGER | - | ✅ | 0 | 验证标记：`0` 未验证 / `1` 已验证 |
| `server_type` | TEXT | - | ✅ | - | 服务器类型：`local`（本地）/ `remote`（远程） |
| `labels` | TEXT | - | ✅ | - | 标签列表，JSON 数组（如 `["approved"]`） |
| `created_at` | TEXT | - | ✅ | - | 市场条目创建时间 |
| `raw_issue` | TEXT | - | ✅ | - | GitHub Issue 完整原始数据（JSON） |
| `fetched_at` | TEXT | - | ✅ | - | 最近一次抓取时间 |

**索引：** `name`（按名称查找）、`installed`（筛选已安装）、`server_type`（本地/远程筛选）

---

### 2.4 `mcp_server_logs` — MCP 服务器操作日志表

> 记录 MCP 服务器的安装、卸载、启动、停止、重启等操作日志。

**建表 SQL：**
```sql
CREATE TABLE IF NOT EXISTS mcp_server_logs (
    id          TEXT PRIMARY KEY,                   -- 日志记录 ID（UUID）
    server_id   TEXT NOT NULL,                      -- 服务器 ID（外键 → mcp_market_index.id）
    action      TEXT,                               -- 操作类型：install / uninstall / start / stop / restart / config
    status      TEXT,                               -- 执行状态：start / success / failed
    log_content TEXT,                               -- 日志内容（汇总文本）
    log_file    TEXT,                               -- 对应日志文件路径
    duration    REAL,                               -- 操作耗时（秒）
    server_name TEXT,                               -- 服务器显示名称（冗余）
    repo_url    TEXT,                               -- GitHub 仓库地址（冗余）
    created_at  TEXT,                               -- 创建时间
    updated_at  TEXT                                -- 最后追加时间
);
```

**字段说明：**

| 字段 | 类型 | 主键 | 可空 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| `id` | TEXT | ✅ | ❌ | - | 日志记录唯一标识（UUID） |
| `server_id` | TEXT | - | ❌ | - | 关联服务器 ID，外键指向 `mcp_market_index.id` |
| `action` | TEXT | - | ✅ | - | 操作类型：`install`/`uninstall`/`start`/`stop`/`restart`/`config` |
| `status` | TEXT | - | ✅ | - | 执行状态：`start`（进行中）/`success`/`failed` |
| `log_content` | TEXT | - | ✅ | - | 本次操作收集的日志文本汇总 |
| `log_file` | TEXT | - | ✅ | - | 对应的文件日志路径（保留文件日志） |
| `duration` | REAL | - | ✅ | - | 操作耗时（秒） |
| `server_name` | TEXT | - | ✅ | - | 服务器显示名称（冗余存储） |
| `repo_url` | TEXT | - | ✅ | - | GitHub 仓库地址（冗余存储） |
| `created_at` | TEXT | - | ✅ | - | 操作开始时间 |
| `updated_at` | TEXT | - | ✅ | - | 最后追加日志时间 |

**索引：** `server_id`（按服务器查询操作历史）、`action`（按操作类型筛选）

---

## 三、表之间的关系

### 3.1 关系图示

```
┌──────────────────────┐          ┌──────────────────────────┐
│ history_sessions_    │ 1      N │ history_sessions_        │
│ index                │ ───────> │ messages                 │
│ (会话目录)            │          │ (会话内容)                │
│ id (PK)              │          │ session_id (FK)          │
└──────────────────────┘          └──────────────────────────┘
              
┌──────────────────────┐          ┌──────────────────────────┐
│ mcp_market_index     │ 1      N │ mcp_server_logs          │
│ (市场目录)            │ ───────> │ (操作日志)                │
│ id (PK)              │          │ server_id (FK)           │
└──────────────────────┘          └──────────────────────────┘
```

### 3.2 关系说明

| 关系 | 外键 | 说明 |
|------|------|------|
| 会话目录 1:N 会话内容 | `history_sessions_messages.session_id` → `history_sessions_index.id` | 一个会话包含多条消息；删除会话时级联删除其消息 |
| 市场目录 1:N 操作日志 | `mcp_server_logs.server_id` → `mcp_market_index.id` | 一个服务器有多次操作记录；服务器删除后保留日志作为审计 |

### 3.3 设计要点

- **目录表（`_index`）只存元信息**：保证侧边栏列表查询快速，不扫描消息内容
- **内容表（`_messages`）按会话分页加载**：打开哪个会话才查询哪个会话的消息
- **冗余字段（`server_name`/`repo_url`）**：日志查询无需 JOIN 市场表，提升性能
- **JSON 字段（`labels`/`raw_issue`/`tool_calls`）**：SQLite 存储复杂结构，模型层自动序列化/反序列化

---

## 四、业务架构分层

经典 Repository 模式：

```
业务层 model/services/conversation_model.py     ← 面向业务实体
    ↓ 操作实体对象（ChatSession / ChatMessage）
实体层 model/entities/                          ← 🆕 业务纯数据对象
    ├── base.py（BaseEntity 基类：to_dict/from_dict，自动 datetime 还原）
    ├── chat_session.py（ChatSession 会话实体）
    ├── chat_message.py（ChatMessage 消息实体）
    └── mcp_server_log.py（MCPServerLog 日志实体）
    ↓ 经仓库持久化
仓库层 storage/repositories/*_repo.py           ← 持有 db，原生 SQL
    ├── conversation_repo.py（self.db = Database()）
    ├── message_repo.py
    ├── mcp_market_repo.py
    └── mcp_server_logs_repo.py
    ↓
数据库层 storage/                               ← 连接池 + SQL 执行 + 原生 SQL 建表
    └── base_db.py / database.py
```

| 层 | 持有 | 职责 |
|----|------|------|
| 业务层 | 实体对象 | 业务逻辑，创建/修改实体 |
| 实体层 | 无（纯数据） | 业务字段 + to_dict/from_dict（datetime 自动转换） |
| 仓库层 | `self.db = Database()` | 原生 SQL CRUD + 字段/类型转换 |
| 数据库层 | 连接池 | 连接管理 + SQL 执行 + 事务 + 初始化 |

---

## 五、数据库业务逻辑

### 5.1 连接管理

**BaseDatabase（基类）：**
- 管理数据库文件路径（`user_config/database/agent.db`）
- 内置 **ConnectionPool 连接池**（默认最大 10，最小 2）
- 启用 **WAL 模式**（`PRAGMA journal_mode=WAL`）支持并发读写
- 设置 **busy_timeout**（默认 5 秒）避免锁等待异常
- 提供 `execute()` / `query()` / `executemany()` 基础 SQL 方法（自动「获取独立连接 → 执行 → 归还」）

```python
class BaseDatabase:
    _instance = None
    _db_filename = "agent.db"

    def _acquire(self) -> sqlite3.Connection:
        """从连接池获取独立连接（内部使用）"""

    def _release(self, conn):
        """归还连接到连接池（内部使用）"""

    def execute(self, sql, params=()):
        conn = self._acquire()   # 获取独立连接
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount
        finally:
            self._release(conn)  # 用完归还

    def query(self, sql, params=()):
        conn = self._acquire()
        try:
            cursor = conn.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            self._release(conn)
```

**ConnectionPool（连接池）：**
- 固定容量连接池（默认最大 10，最小 2）
- `acquire(timeout)`：获取连接，带超时
- `release(conn)`：归还连接，自动回滚未完成事务
- `_is_valid(conn)`：连接有效性检查（`SELECT 1`）
- **已接入 BaseDatabase**：每个 SQL 操作（`execute/query/query_one/query_value/executemany`）自动「获取独立连接 → 执行 → 归还」
- **多线程安全**：每个线程/操作持有独立连接，事务互不干扰（实测 20 线程并发写入 + 40 线程混合读写全部成功）
- `BaseDatabase.connect()` 为兼容入口，配合 `release_conn()` 手动归还
- `TransactionManager` 使用 `_create_connection()` 创建独立事务连接，不占用连接池

### 5.2 事务管理

**TransactionManager（事务管理器）：**
- 使用 `with db.transaction() as conn:` 语法
- 正常退出自动 `COMMIT`
- 异常退出自动 `ROLLBACK`
- 每次事务使用独立连接，不污染连接池

```python
with database.transaction() as conn:
    conn.execute("INSERT INTO ...")
    conn.execute("UPDATE ...")
    # 任何异常自动回滚，正常则提交
```

### 5.3 实体构建（Entity）

**BaseEntity（实体基类）：**
- 子类继承并声明业务字段（纯数据对象，不含 SQL）
- 提供 `to_dict()` / `from_dict()` / `to_json()` 序列化
- `from_dict()` 自动将数据库时间字符串还原为 datetime

```python
class ChatSession(BaseEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title: str = kwargs.get("title", "新对话")
        self.model: str = kwargs.get("model", "")
        self.message_count: int = kwargs.get("message_count", 0)
        self.token_count: int = kwargs.get("token_count", 0)
        self.status: str = kwargs.get("status", "active")
```

### 5.4 数据访问（Repository CRUD 操作）

**仓库持有 db + 原生 SQL：**

```python
class ConversationRepository:
    def __init__(self):
        self.db = Database()   # 持有数据库（连接池）

    def save(self, item: ChatSession) -> bool:
        # 实体 → dict（datetime 转字符串）→ 原生 SQL 写入

    def get(self, item_id: str) -> ChatSession:
        # 原生 SQL 查询 → dict → ChatSession.from_dict（datetime 自动还原）

    def get_all(self) -> List[ChatSession]: ...
    def delete(self, item_id: str) -> bool: ...
```

| 仓库 | 表层 | 返回 |
|------|------|------|
| `conversation_repo.py` | `history_sessions_index` | `ChatSession` |
| `message_repo.py` | `history_sessions_messages` | `ChatMessage` |
| `mcp_market_repo.py` | `mcp_market_index` | dict（前端格式） |
| `mcp_server_logs_repo.py` | `mcp_server_logs` | `MCPServerLog` |

### 5.5 初始化与数据迁移

**数据库全局初始化（应用启动时自动，仅建空表）：**

```
main.py 入口
  └→ storage.initializer.DatabaseInitializer.initialize()（集中封装）
       └→ storage.database.Database()（全局初始化）
            ├─ sqlite3.connect() → 自动创建 agent.db（若不存在）
            └─ ensure_tables() → 原生 SQL 执行 CREATE TABLE IF NOT EXISTS + 索引（幂等）
                 ├─ 全新环境：自动创建 4 张空表 + 索引
                 ├─ 正常启动：表已存在则跳过，零副作用
                 └─ 部分缺失：自动补建缺失的表
```

**设计原则：**
- **建表 = 启动时自动**（`CREATE TABLE IF NOT EXISTS` 幂等，无副作用）
- **初始化逻辑集中封装**在 `storage/initializer.py` 的 `DatabaseInitializer.initialize()`，main.py 只调用这一个入口
- **初始化不在 MCPBridge 中**：数据库职责与 MCP 业务解耦
- **数据迁移 = 手动脚本**（仅在从旧版升级时需要）

**手动数据迁移（升级时执行）：**

```bash
python scripts/migrate_db.py            # 查看当前状态
python scripts/migrate_db.py --migrate  # 执行迁移（建表 + 旧数据导入）
```

迁移流程：
```
mcp.db (旧)
  └── mcp_market 表 ──→ agent.db (新)
                        └── mcp_market_index 表
```

迁移逻辑：
- 读取旧 `mcp.db` 中 `mcp_market` 表全部数据
- 逐条插入到新表 `mcp_market_index`
- 用 `PRAGMA user_version` 标记版本，避免重复迁移

---

## 六、调用示例

### 6.1 保存历史会话

```python
from model.entities.chat_session import ChatSession
from model.entities.chat_message import ChatMessage
from storage.repositories.conversation_repo import ConversationRepository
from storage.repositories.message_repo import MessageRepository

conv_repo = ConversationRepository()
msg_repo = MessageRepository()

# 创建会话（实体）
conv = ChatSession(title="与 DeepSeek 的对话", model="deepseek-chat")
conv_repo.save(conv)

# 保存消息（实体）
msg = ChatMessage(session_id=conv.id, role="user", content="你好，帮我分析这段代码")
msg_repo.save(msg)

msg2 = ChatMessage(session_id=conv.id, role="assistant", content="好的，请提供代码...")
msg_repo.save(msg2)
```

### 6.2 查询历史会话

```python
from storage.repositories.conversation_repo import ConversationRepository
from storage.repositories.message_repo import MessageRepository

conv_repo = ConversationRepository()   # 返回 ChatSession 实体（created_at 为 datetime）
msg_repo = MessageRepository()         # 返回 ChatMessage 实体

# 获取所有会话（按创建时间倒序）
sessions = conv_repo.get_all()

# 加载某个会话的全部消息（按时间正序）
messages = msg_repo.get_by_session(session_id, order_by="created_at ASC")
```

### 6.3 查询 MCP 市场数据

```python
from storage.repositories.mcp_market_repo import MCPMarketRepository

repo = MCPMarketRepository()

# 获取所有市场项（前端格式，camelCase）
items = repo.get_all()

# 按 ID 查询单个服务器
server = repo.get_by_id("mcp-123")
```

### 6.4 记录 MCP 操作日志

```python
from model.entities.mcp_server_log import MCPServerLog
from storage.repositories.mcp_server_logs_repo import MCPServerLogsRepository

logs_repo = MCPServerLogsRepository()

# 创建日志实体
log = MCPServerLog(
    server_id="mcp-123",
    action="install",
    status="start",
    server_name="My MCP Server",
    repo_url="https://github.com/example/mcp-server",
)
logs_repo.save(log)

# 更新日志（追加完成状态）
log.status = "success"
log.duration = 45.3
log.log_content = "✅ 安装完成 (code=0)"
logs_repo.save(log)
```

### 6.5 使用事务批量操作

```python
from storage.transaction import transaction

with transaction(db) as conn:
    # 批量保存会话 + 消息（要么全部成功，要么全部回滚）
    conn.execute(
        "INSERT INTO history_sessions_index (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("s1", "批量会话", datetime.now().isoformat(), datetime.now().isoformat())
    )
    conn.execute(
        "INSERT INTO history_sessions_messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("m1", "s1", "user", "内容", datetime.now().isoformat())
    )
```

---

## 七、设计原则与最佳实践

1. **单一数据库**：所有业务数据统一存 `agent.db`，避免多库管理
2. **目录/内容分离**：`_index` 表存元信息，`_messages` 表存详情，查询高效
3. **JSON 序列化内置**：模型层自动处理复杂字段，业务代码无需关心
4. **连接池复用**：避免频繁建连开销
5. **WAL 模式**：支持多线程并发读写
6. **事务保护**：批量操作原子性
7. **日志表冗余**：日志查询不需要 JOIN，性能更优