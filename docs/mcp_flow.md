# MCP 业务流程文档

## 1. 概述

MCP（Model Context Protocol，模型上下文协议）是本系统中连接外部工具服务的核心机制。系统作为 **MCP Host**，通过标准 JSON-RPC 协议与各种 MCP 服务器通信，将外部能力（工具）注入到 AI 对话中。

### 支持的传输类型

| 传输方式 | 说明 | 适用场景 |
|---------|------|---------|
| **stdio** | 启动本地子进程，通过标准输入/输出进行 JSON-RPC 通信 | 本地安装的 MCP 服务器（Node.js / Python 项目） |
| **http** | 通过 HTTP/SSE 与远程 MCP 服务通信 | 远程托管的 MCP 服务，支持 API Key 认证 |

### 核心能力

- **MCP 市场**：从 GitHub Issues 拉取、浏览、安装/卸载 MCP 服务器
- **服务器管理**：启动、停止、重启、批量启停本地/远程服务器
- **工具注入**：MCP 服务器连接成功后自动发现工具并注册到 AI 客户端
- **AI 工具调用**：AI 在对话中调用 MCP 工具，由调度器路由到正确的服务器执行

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        View 层 (前端 JS)                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ mcp-market  │ │ mcp-local   │ │ mcp-remote  │ │ mcp-shared│ │
│  │ (市场页)     │ │ (本地页)     │ │ (远程页)     │ │ (共享逻辑) │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                        │ QWebChannel (pyqtSlot)                  │
└────────────────────────┼──────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Bridge 层 (bridge/mcp_bridge.py)               │
│  ► 市场拉取/安装/卸载     ► 服务器启停/重启                         │
│  ► 工具发现与注册        ► 配置读写/增量更新                        │
│  ► 日志推送/API Key 弹窗  ► AI 安装助手工具                         │
└────────────────────────┼──────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              MCPHost (tools/mcp/host.py) — 单例                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 职责：客户端生命周期管理 + 工具汇总 + 工具路由                  │ │
│  │                                                             │ │
│  │  ┌──────────────────┐      ┌──────────────────┐             │ │
│  │  │ MCPLocalClient   │      │ MCPHTTPClient    │             │ │
│  │  │ (stdio 子进程)    │      │ (HTTP/SSE 远程)   │             │ │
│  │  └──────────────────┘      └──────────────────┘             │ │
│  └────────────────────────────────────────────────────────────┘ │
│        配置读写: user_config/defaults/mcp_servers.json           │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────────┐
│        AI 调度层 (ai/mcp_dispatcher.py — MCPDispatcher)           │
│  路由策略：① 已注册处理器（优先） → ② MCPHost 路由到对应客户端      │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────────┐
│        数据层 (data/)                                             │
│  mcp_db.py (mcp.db 连接)  +  mcp_market_repo.py (市场数据 CRUD)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块与职责

| 模块 | 文件 | 职责 |
|------|------|------|
| **MCP 桥接** | `bridge/mcp_bridge.py` | 前后端交互核心：市场管理、服务器生命周期、工具注册、AI 安装助手、日志推送 |
| **MCP 主机** | `tools/mcp/host.py` | 单例管理所有客户端：启动/停止、工具汇总、按工具名路由、配置文件读写 |
| **本地客户端** | `tools/mcp/local_client.py` | 管理单个 stdio 子进程，通过 JSON-RPC（initialize → tools/list → tools/call）通信 |
| **HTTP 客户端** | `tools/mcp/http_client.py` | 通过 HTTP/SSE 连接远程 MCP 服务，支持 API Key 认证、session 管理 |
| **协议层** | `tools/mcp/protocols/` | JSON-RPC 消息构建与解析（initialize、tools/list、tools/call） |
| **MCP 调度器** | `ai/mcp_dispatcher.py` | AI 工具调用路由：优先注册处理器，回退到 MCPHost 路由 |
| **控制器** | `controller/mcp_controller.py` | 兼容层，转发到 MCPBridge |
| **数据库** | `data/mcp_db.py` | mcp.db 连接管理（单例） |
| **市场仓储** | `data/repositories/mcp_market_repo.py` | mcp_market 表 CRUD 操作 |
| **前端-市场** | `view/js/mcp-market.js` | 市场列表渲染、搜索/分类筛选、安装/卸载交互 |
| **前端-本地** | `view/js/mcp-local.js` | 本地服务器扫描、添加本地 MCP、表单填充 |
| **前端-远程** | `view/js/mcp-remote.js` | 远程 HTTP 服务器添加、渲染 |
| **前端-共享** | `view/js/mcp-shared.js` | 日志推送、状态刷新、API Key 弹窗、服务器启停、JSON 配置编辑、安装分析启动 |

---

## 4. 核心业务流程图

### 4.1 服务器生命周期管理

```
┌─────────┐    启动     ┌─────────┐    停止     ┌─────────┐
│ 停止状态 │ ─────────► │ 运行中   │ ─────────► │ 停止状态 │
└─────────┘            └─────────┘            └─────────┘
     ▲                    │     │                   │
     │                    │     └─── 重启 ──────────┘
     │                    ▼
     │             工具发现并注册到 AI
     └─── 启动失败 ─── 日志记录 + 测试运行诊断
```

**启动流程** (`startMCPServer`)：
1. 前端调用 → `MCPBridge.startMCPServer(server_id)`
2. 读取 `mcp_servers.json` 配置，设置 `enabled = true`
3. 调用 `MCPHost.register_client()` 注册客户端
   - **stdio**：解析命令 → 启动子进程 → `initialize` → `initialized` → `tools/list`
   - **http**：连接远程 URL → session 建立 → `initialize` → `initialized` → `tools/list`
4. 成功后调用 `_register_mcp_tools_to_ai()`：
   - 遍历 `list_tools()` 获取工具列表
   - 每个工具注册一个异步 handler 到 `MCPDispatcher`
   - 调用 `ai_client.register_mcp_handler()` 通知 AI 更新工具
5. 前端回调 `mcpFinishInstall(id, 0)` + `loadMCPServers()` 刷新 UI

**停止流程** (`stopMCPServer`)：
1. `MCPHost.unregister_client()` → 清理子进程/断开连接
2. 配置中设置 `enabled = false`
3. 刷新前端

**配置增量更新** (`saveMCPConfig`)：
1. 对比新旧配置，找出需要停止的（配置变化/已删除）和需要启动的（新增/启用的）
2. 先停止变化的服务器，再启动需要的服务器
3. 避免全量重启，只重启有变动的部分

**后台并发加载**：应用启动时，按 `AGENT_MCP_PARALLEL`（默认 4）并发启动所有启用的服务器。

**状态推送机制**：前端不主动轮询。MCPHost 状态变化时通过 `MCPHost.on_status_change()` 回调触发 `loadMCPServers()` 刷新；前端仅在初始化 3 秒后拉取一次初始状态。

---

### 4.2 MCP 市场安装流程

```
┌────────────────────────────────────────────────────────────────┐
│  ① 市场数据拉取 (refreshMCPMarket)                               │
│     ├─ GitHub Issues API (open + closed/approved 分页拉取)        │
│     ├─ 解析 Issue → 市场项（名称/仓库/描述/类型/标签）             │
│     └─ 存储到 mcp.db (mcp_market 表)                             │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  ② 用户点击安装 (installMCPFromMarket)                           │
│     ├─ 从数据库/缓存获取 GitHub 仓库 URL                          │
│     ├─ git clone --depth 1 到 tools/mcp/server/[目录名]           │
│     ├─ 自动检测并安装依赖（pnpm/yarn/npm）                        │
│     └─ 注册日志路径到服务器目录                                    │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  ③ AI 智能分析（前端触发 startMCPInstallAnalysis，5 步流程）       │
│     ├─ 1. directory_ops(Readdir): 列出目录文件                     │
│     │     📁 = 目录（跳过）| 📄 = 普通文件（可读取）                  │
│     ├─ 2. file_ops(Open): 打开读取关键文件内容                      │
│     │     （.mcp.json / package.json / pyproject.toml / 入口文件）  │
│     ├─ 3. run_command: 自动安装依赖                                │
│     │     requirements.txt → pip install /                        │
│     │     package.json → npm install /                            │
│     │     pyproject.toml → pip install -e .                       │
│     ├─ 4. 若需要 API Key → mcp_env_setup → 前端弹窗                │
│     │     -> confirmEnvVars 保存环境变量                           │
│     └─ 5. mcp_finalize_install(config_json): 提交最终配置          │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  ④ 配置写入与启动 (finalizeMCPInstall)                            │
│     ├─ 合并 AI 检测的配置 + 用户确认的环境变量                     │
│     ├─ 写入 mcp_servers.json                                     │
│     ├─ 后台线程 register_client() 启动服务器                      │
│     ├─ 工具发现 → 注册到 AI                                      │
│     └─ mcpFinishInstall(id, 0) 回调前端更新安装状态               │
└────────────────────────────────────────────────────────────────┘
```

**卸载流程** (`uninstallMCPFromMarket`)：
1. 停止服务（`unregister_client`）
2. 删除配置（`remove_remote_server`）
3. 删除项目目录（`shutil.rmtree`）
4. 更新数据库 installed 状态

---

### 4.3 AI 工具调用链路

```
用户消息 → AI 客户端 → LLM 返回工具调用
                              │
                              ▼
                    MCPDispatcher.execute()
                              │
              ┌───────────────┴───────────────┐
              │                               │
     ① 注册的处理器存在？              ② MCPHost 路由
      （MCPBridge 注册的           （get_client_for_tool
       异步 handler）              遍历客户端找匹配工具）
              │                               │
              └───────────────┬───────────────┘
                              ▼
                    MCPLocalClient.call_tool()
                    或 MCPHTTPClient.call_tool()
                              │
                         JSON-RPC tools/call
                              │
                              ▼
                    解析执行结果 → 返回文本
                              │
                              ▼
              AI 接收结果 → 继续生成回复 → 返回前端
```

**路由策略优先级**：
1. `MCPDispatcher._handlers` 中已注册的异步处理器（启动服务器时注册）
2. 回退到 `MCPHost.execute_tool()`：先查 `_tool_handlers`，再遍历客户端 `get_client_for_tool()`

**超时机制**：单次工具调用默认 60 秒超时，超时返回错误信息。

**进程崩溃自动恢复**：`MCPLocalClient.call_tool()` 检测到子进程已退出时，自动尝试重启并重新调用工具。

---

### 4.4 本地/远程服务器添加流程

**添加本地服务器** (前端 `mcp-local.js`)：
```
① 扫描 tools/mcp/server/ 目录 (getLocalServerDirs)
      │
② 选择目录 → detectLocalServer() 自动检测
      │  ├─ .mcp.json → 检测 HTTP 远程配置
      │  ├─ package.json → 检测 bin/main 入口、包管理器
      │  └─ pyproject.toml → 检测 Python 入口
      ▼
③ 确认表单（命令/参数/工作目录/传输方式）→ addMCPServer
      ▼
④ MCPHost.add_remote_server() 或配置写入 → 启动
```

**添加远程服务器** (前端 `mcp-remote.js`)：
```
① 输入 server_id + URL
      ▼
② addMCPServer(server_id, name, url, description)
      ▼
③ MCPHost.add_remote_server() → 写入配置 (transport=http)
      ▼
④ 连接测试 + 工具发现 + 注册到 AI
```

---

## 5. 配置说明 — `user_config/defaults/mcp_servers.json`

```json
{
  "mcpServers": {
    "server-id": {
      "transport": "stdio | http",
      "enabled": true,
      "auto_start": true,
      "name": "显示名称",
      "description": "服务器描述",
      "command": "node | python | npx ...",
      "args": ["参数数组"],
      "cwd": "工作目录（自动转为绝对路径）",
      "env": { "API_KEY": "环境变量" },
      "url": "HTTP 远程服务的 URL（仅 http 传输）",
      "githubRepoUrl": "来源仓库（从市场安装时自动填充）"
    }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `transport` | string | ✓ | `stdio`（本地子进程）或 `http`（远程服务），缺省时自动推断（有 url 则 http） |
| `enabled` | bool | | 是否启用，`false` 时不会自动启动 |
| `auto_start` | bool | | 是否随应用自动启动 |
| `command` | string | stdio 必填 | 启动命令（如 `node`、`python`、`npx`） |
| `args` | array | | 命令行参数（如 `["dist/index.js"]`） |
| `cwd` | string | | 工作目录，相对路径会自动转为绝对路径 |
| `env` | object | | 传递给子进程的环境变量 |
| `url` | string | http 必填 | 远程服务端点 URL |
| `name` / `description` | string | | 展示信息 |
| `githubRepoUrl` | string | | 来源 GitHub 仓库（市场安装自动填充） |

**系统命令白名单**（不进行路径解析）：`node`, `npx`, `npm`, `yarn`, `pnpm`, `uv`, `python`, `python3`, `pip`, `pip3`

---

## 6. 数据库设计 — `data/database/mcp.db`

### mcp_market 表（MCP 市场数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT (PK) | 市场项 ID（`mcp-{issue_number}` 或目录名） |
| `name` | TEXT | 服务器名称 |
| `title` | TEXT | Issue 标题 |
| `github_repo_url` | TEXT | GitHub 仓库地址 |
| `logo` | TEXT | Logo 图片 URL |
| `description` | TEXT | 描述（前 500 字符） |
| `author` | TEXT | 提交者 GitHub 用户名 |
| `issue_number` | INTEGER | 对应 GitHub Issue 编号 |
| `installed` | INTEGER | 是否已安装（0/1） |
| `tested` | INTEGER | 是否已测试（0/1） |
| `server_type` | TEXT | 类型：`local` / `remote` / `unknown` |
| `labels` | TEXT | JSON 数组（GitHub labels） |
| `created_at` | TEXT | Issue 创建时间 |
| `raw_issue` | TEXT | 原始 Issue JSON（完整备份） |
| `fetched_at` | TEXT | 拉取时间 |

---

## 7. 前端交互接口清单（MCPBridge 方法）

### 服务器管理

| 方法 | 说明 |
|------|------|
| `getMCPServers()` | 获取所有服务器列表（含 online 状态、工具数） |
| `getAllServersStatus()` | 获取所有客户端实时状态 |
| `getServerStatus(server_id)` | 获取单个服务器状态 |
| `startMCPServer(server_id)` | 启动服务器 |
| `stopMCPServer(server_id)` | 停止服务器 |
| `restartMCPServer(server_id)` | 重启服务器 |
| `startAllMCPServers()` | 启动所有启用的服务器 |
| `stopAllMCPServers()` | 停止所有服务器 |

### 市场管理

| 方法 | 说明 |
|------|------|
| `getMCPMarket()` | 获取市场列表（优先本地数据库） |
| `refreshMCPMarket()` | 从 GitHub 刷新市场数据 |
| `installMCPFromMarket(item_id, repo_url)` | 从市场安装（clone + AI 分析） |
| `uninstallMCPFromMarket(item_id, cmd)` | 卸载（停止 + 删配置 + 删目录） |
| `refreshMarketFromUrl(url)` | 从任意 URL 抓取市场卡片 |

### 本地/远程添加

| 方法 | 说明 |
|------|------|
| `getLocalServerDirs()` | 列出 `tools/mcp/server/` 下的项目目录 |
| `detectLocalServer(dir_name)` | 自动检测本地项目（入口/类型/包管理器） |
| `addMCPServer(server_id, name, url, desc)` | 添加远程服务器 |
| `removeMCPServer(server_id)` | 删除服务器配置 |

### 工具与 AI 集成

| 方法 | 说明 |
|------|------|
| `getMCPTools()` | 获取所有 MCP 工具（OpenAI 格式） |
| `getMCPToolList(server_id)` | 获取指定服务器的工具列表 |
| `register_tools_to_dispatcher(dispatcher)` | 注册工具到调度器 |

### 配置管理

| 方法 | 说明 |
|------|------|
| `getMCPConfig()` | 读取完整配置 JSON |
| `saveMCPConfig(config_json)` | 保存配置（智能增量更新，只重启有变动的服务器） |

### AI 安装助手（AI 工具）

| 工具/方法 | 说明 |
|------|------|
| `directory_ops(Readdir)` | 列出服务器目录文件（AI 流程第 1 步） |
| `file_ops(Open)` | 读取服务器文件内容（AI 流程第 2 步） |
| `run_command` | 在服务器目录执行安装依赖命令（AI 流程第 3 步） |
| `mcp_env_setup(server_id)` | 请求 API Key → 触发前端弹窗（AI 流程第 4 步） |
| `mcp_finalize_install(config_json)` | 完成安装：写配置 + 启动（AI 流程第 5 步） |
| `confirmEnvVars(server_id, env_json)` | 用户确认环境变量后的回调保存 |
| `listServerFiles(server_id)` | 列出服务器目录文件（桥接方法，供 AI 工具底层调用） |
| `readServerFile(server_id, filename)` | 读取服务器文件内容（桥接方法，供 AI 工具底层调用） |

### 日志与工具

| 方法 | 说明 |
|------|------|
| `getMCPLog(item_id)` | 获取安装日志 |
| `read_mcp_file(filename)` / `write_mcp_file(filename, content)` | 读写 mcp_server 目录文件 |
| `openExternalUrl(url)` | 在系统浏览器打开 URL |

---

## 8. 异常与边界处理

| 场景 | 处理策略 |
|------|---------|
| **工具执行超时** | `MCPDispatcher` 默认 60 秒超时，返回 `❌ 执行超时` |
| **子进程崩溃** | `MCPLocalClient.call_tool()` 检测到进程退出时自动重启并重试 |
| **HTTP 401 未认证** | `MCPHTTPClient` 触发回调 → 前端弹出 API Key 输入框 → `confirmEnvVars` 保存 → 重试 |
| **服务器未运行** | 返回 `❌ 服务器未运行，请先启动该 MCP 服务器` |
| **工具未安装** | 返回 `⚠️ 工具未安装，请先安装对应的 MCP 服务器` |
| **Windows 命令兼容** | 自动解析 `npx`/`.cmd`/`.bat`，PATH 自动补充 node/npm/python 目录 |
| **事件循环冲突** | 子进程绑定独立事件循环，同步调用通过线程池执行，避免阻塞 AI 异步循环 |
| **后台并发安全** | 遍历 `_clients` 前先快照，避免字典在加载线程中并发修改 |
| **配置变更** | `saveMCPConfig` 智能对比，只重启有变动的服务器 |
| **克隆失败** | 自动重试 1 次 → 提示检查网络/Git/仓库地址 |
| **安装依赖超时** | 超时（180 秒）强制终止并重试 1 次 |
| **目录已存在** | 跳过 git clone，直接进入 AI 分析步骤 |
| **环境变量优先级** | 用户确认的 env 始终覆盖 AI 传入的同名变量 |