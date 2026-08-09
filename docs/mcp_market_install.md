# MCP 市场安装流程文档

## 1. 概述

本系统内置 **MCP 市场（MCP Marketplace）**，允许用户无需手动配置即可一键安装 MCP（Model Context Protocol）服务器。

市场数据来源于 GitHub Issues（[cline/mcp-marketplace](https://github.com/cline/mcp-marketplace)），通过提交标准格式的 Issue 来发布 MCP 服务器。用户在市场中点击**安装**后，系统会自动完成：

1. **获取源码**：`git clone` 项目到本地目录
2. **依赖安装**：自动检测并安装 Node / Python 依赖
3. **AI 智能分析**：AI 自动读取项目文件、识别入口、检测所需环境变量
4. **配置写入**：生成可用的 MCP 服务器配置
5. **启动与注入**：启动服务器、发现工具并注入到 AI 客户端

> 相比传统手动编辑配置文件安装 MCP 服务器，市场安装完全自动化，AI 替代了人工分析项目结构和入口的繁琐步骤。

---

## 2. 整体架构

```
┌───────────────────────────────────────────────────────────────────┐
│                        View 层 (前端 JS)                            │
│  ┌─────────────────────┐  ┌─────────────────────────────────────┐ │
│  │  mcp-market.js      │  │  mcp-shared.js                      │ │
│  │  - 市场列表 / 安装按钮 │  │  - 日志推送 / 状态刷新 / API Key 弹窗 │ │
│  └─────────────────────┘  └─────────────────────────────────────┘ │
│                        │  QWebChannel (pyqtSlot)                  │
└────────────────────────┼────────────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────────┐
│               Bridge 层 (bridge/mcp_bridge.py)                      │
│  ┌─────────────────────┐  ┌─────────────────────────────────────┐ │
│  │  市场管理             │  │  AI 安装助手工具                      │ │
│  │  installMCPFromMarket│  │  finalizeMCPInstall                 │ │
│  │  uninstallMCPFromMarket│ │  confirmEnvVars                     │ │
│  │  refreshMCPMarket    │  │  listServerFiles / readServerFile   │ │
│  └─────────────────────┘  └─────────────────────────────────────┘ │
└────────────────────────┼────────────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────────┐
│              MCPHost (tools/mcp/host.py) — 单例                     │
│  ┌─────────────────────┐  ┌─────────────────────────────────────┐ │
│  │  register_client     │  │  unregister_client                  │ │
│  │  (启动 stdio/http)   │  │  (停止服务器)                        │ │
│  └─────────────────────┘  └─────────────────────────────────────┘ │
│        配置读写: user_config/defaults/mcp_servers.json              │
└────────────────────────┼────────────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────────┐
│        数据层 (storage/)                                            │
│  database.py + repositories/mcp_market_repo.py                     │
│  (market 数据库连接)  (mcp_market 表 CRUD)                          │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. 市场数据加载流程

```
用户进入市场页 / 点击「刷新」
        │
        ▼
① refreshMCPMarket()  ←── 前端调用 Bridge 方法（异步线程执行）
        │
        ▼
② 从 GitHub Issues API 分页拉取（_fetch_github_issues）
        ├─ GET https://api.github.com/repos/cline/mcp-marketplace/issues
        │   ├─ ?state=open&per_page=100&sort=created&direction=desc
        │   └─ ?state=closed&per_page=100&sort=created&direction=desc&labels=approved
        │
        ▼
③ 解析每个 Issue（_parse_issue_to_market_item）
        ├─ 标题需以 [Server Submission] 开头，否则跳过
        ├─ 从 Issue body 中提取：
        │   ├─ ### GitHub Repository URL → 仓库地址
        │   ├─ ### Logo Image → Logo 图片
        │   └─ ### Additional Information → 描述信息
        ├─ 生成市场项 ID：mcp-{issue_number}
        └─ 判定类型：remote（包含 Streamable HTTP） / local / unknown
        │
        ▼
④ 保存到 SQLite 数据库 mcp_market 表（upsert_many）
        │
        ▼
⑤ 前端回调 _onMCPMarketRefreshed → 渲染市场卡片
        ├─ 支持搜索（名称/描述/作者）
        ├─ 支持分类筛选（全部/本地/网络/已验证/待审核）
        └─ 显示安装状态（已安装→显示卸载按钮和启停控制）
```

**市场数据字段**（`mcp_market` 表）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT (PK) | 市场项 ID（`mcp-{issue_number}`） |
| `name` / `title` | TEXT | 服务器名称 / Issue 标题 |
| `github_repo_url` | TEXT | GitHub 仓库地址 |
| `logo` | TEXT | Logo 图片 URL |
| `description` | TEXT | 描述（前 500 字符） |
| `author` | TEXT | 提交者 GitHub 用户名 |
| `issue_number` | INTEGER | 对应 GitHub Issue 编号 |
| `installed` | INTEGER | 是否已安装（0/1） |
| `tested` | INTEGER | 是否已测试（0/1） |
| `server_type` | TEXT | 类型：`local` / `remote` / `unknown` |
| `labels` | TEXT | JSON 数组（GitHub labels） |
| `raw_issue` | TEXT | 原始 Issue JSON（完整备份） |
| `fetched_at` | TEXT | 拉取时间 |

---

## 4. 安装完整流程

```
┌─────────────────────────────────────────────────────────────────────┐
│  ① 用户点击「安装」按钮                                                 │
│     view/js/mcp-market.js → toggleMCPInstall(id)                    │
│            │                                                         │
│            ▼                                                         │
│  ② 前端调用 Bridge 方法                                               │
│     mcp_bridge.installMCPFromMarket(id, githubRepoUrl)               │
│            │                                                         │
│            ▼                                                         │
│  ③ 后台线程 worker() 执行（不阻塞 UI）                                 │
│     ├─ 清空日志 → 初始化安装上下文                                     │
│     ├─ 步骤 1/2: 获取源码（git clone）                                │
│     └─ 步骤 2/2: AI 智能分析                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.1 步骤 ①：用户点击安装（前端）

前端逻辑位于 `view/js/mcp-market.js` 的 `toggleMCPInstall(id)`：

```
toggleMCPInstall(id)
    ├─ 查找市场数据 item
    ├─ 已安装？ → 走卸载流程（见第 5 节）
    └─ 未安装？ → 调用后端安装：
        ├─ showMCPLog(id, '📦 正在安装: {name}')
        ├─ mcp_bridge.installMCPFromMarket(id, item.githubRepoUrl)
        └─ showToast('📦 安装中: {name}（查看日志）')
```

### 4.2 步骤 ②：获取源码（git clone）

后端核心位于 `bridge/mcp_bridge.py` 的 `installMCPFromMarket(item_id, repo_url)`：

```
worker() 线程执行：
    │
    ├─ 获取仓库信息
    │   ├─ repo_url 为空时从数据库/缓存查询（_get_market_item）
    │   └─ install_name 从市场项 name 字段获取
    │
    ├─ 计算目标目录
    │   ├─ repo_dir_name = 仓库名（去除 .git、小写）
    │   └─ clone_dir = tools/mcp/server/{repo_dir_name}
    │   └─ config_id = repo_dir_name（配置中的服务器 ID）
    │
    ├─ 注册日志路径（_register_log_path）
    │   └─ 日志写入服务器目录: {name}_{时间戳}.log
    │
    ├─ 检查磁盘剩余空间（显示 GB 信息）
    │
    ├─ git clone --depth 1（浅克隆 + 多级加速链）
    │   ├─ 候选通道：用户自定义镜像 → 直连 → ghfast.top → gh-proxy.com → moeyy → ghproxy.net
    │   ├─ 每个通道只尝试一次（30 秒拨号超时），自动切换到下一个可用源
    │   ├─ 自动检测系统 HTTPS_PROXY / HTTP_PROXY 环境变量并传给 git
    │   ├─ 目录已存在 → 跳过克隆
    │   ├─ 克隆成功后 → _auto_install_deps()（见 4.3）
    │   └─ 全部通道失败 → 输出详细诊断信息（列出每个尝试过的通道）
    │
    └─ 克隆失败 → 提示检查网络/配置 GitHub 镜像前缀，结束
```

### 4.3 步骤 ③：自动安装依赖

克隆成功后自动检测项目类型并安装依赖（`_auto_install_deps`）：

| 检测条件 | 命令 | 说明 |
|---------|------|------|
| `pnpm-workspace.yaml` 或 `pnpm-lock.yaml` | `pnpm install` | pnpm 项目 |
| `yarn.lock` | `yarn install` | Yarn 项目 |
| `package.json` | `npm install` | npm 项目 |
| 以上都没有 | 跳过 | Python 项目依赖由 AI 分析阶段处理 |

- 执行超时：**180 秒**，超时强制终止并重试 1 次
- 实时输出安装日志到前端

### 4.4 步骤 ④：AI 智能分析

源码获取成功后，保存安装上下文并启动 AI 分析：

```python
self._install_context = {
    "item_id": item_id,          # 市场项 ID（mcp-{number}）
    "name": install_name,        # 显示名称
    "repo_url": install_url,     # GitHub 仓库 URL
    "clone_dir": clone_dir,      # 克隆目录绝对路径
    "config_id": repo_dir_name,  # 配置 ID（目录名）
    "start_time": start_time,
}
```

前端收到 `startMCPInstallAnalysis(...)` 后，AI 执行以下 **5 步分析流程**：

```
┌────────────────────────────────────────────────────────────────────┐
│  ① directory_ops (Readdir) — 列出目录文件                             │
│     ├─ 📁 = 目录（跳过）                                              │
│     └─ 📄 = 普通文件（可读取）                                        │
│                    ▼                                                 │
│  ② file_ops (Open) — 打开读取关键文件内容                              │
│     ├─ .mcp.json（HTTP 远程配置）                                     │
│     ├─ package.json（Node 入口/bin）                                  │
│     ├─ pyproject.toml（Python 入口）                                  │
│     └─ 其他入口文件 / README / 配置示例                                │
│                    ▼                                                 │
│  ③ execute_system_command — 自动安装 Python 依赖                      │
│     ├─ requirements.txt → pip install                               │
│     ├─ pyproject.toml  → pip install -e .                           │
│     └─ package.json    → npm install（若步骤②未安装）                  │
│                    ▼                                                 │
│  ④ 若需要 API Key → mcp_env_setup → 前端弹窗                          │
│     ├─ 用户输入 Key → confirmEnvVars(server_id, env_json)            │
│     ├─ 情况1：安装上下文还在 → 保存到 _install_context["env_vars"]     │
│     └─ 情况2：配置已写入但 env 为空 → 直接更新配置文件并重启             │
│                    ▼                                                 │
│  ⑤ mcp_finalize_install(config_json) — 提交最终配置                   │
└────────────────────────────────────────────────────────────────────┘
```

> **环境变量优先级**：用户确认的 env 始终覆盖 AI 传入的同名变量。

### 4.5 步骤 ⑤：配置写入与启动（finalizeMCPInstall）

AI 提交最终配置后，`finalizeMCPInstall(item_id, config_json, extra_info)` 执行：

```
finalizeMCPInstall:
    │
    ├─ 从 _install_context 获取安装上下文（丢失则报错）
    │
    ├─ 合并环境变量
    │   └─ cfg["env"] = {**AI检测的env, **用户确认的env}
    │
    ├─ 构建 server_config
    │   ├─ transport: stdio / http
    │   ├─ enabled: true, auto_start: true
    │   ├─ name / description
    │   ├─ githubRepoUrl（自动填充）
    │   └─ env（合并后的环境变量）
    │
    ├─ 根据 transport 分支：
    │   ├─ HTTP 远程：server_config["url"] = cfg["url"]
    │   └─ STDIO 本地：
    │       ├─ command（如 python / node / npx）
    │       ├─ args（如 ["-m", "mcp_server"]）
    │       └─ cwd → 转为绝对路径
    │
    ├─ 写入配置文件
    │   └─ servers[config_id] = server_config
    │   └─ mgr._write_config(config) → mcp_servers.json
    │
    ├─ 后台线程启动服务器（_start_server）
    │   ├─ register_client(config_id, server_config)
    │   ├─ 登录取工具列表 → 注册到 MCPDispatcher
    │   ├─ ai_client.register_mcp_handler() → 更新 AI 工具
    │   └─ mcpFinishInstall(market_item_id, 0) → 前端刷新
    │
    └─ 持久化 installed 状态到数据库
        └─ db_item["installed"] = True → repo.upsert(db_item)
```

### 4.6 启动后的效果

- 前端市场卡片显示 **🟢 在线** 状态
- 显示已发现的工具列表（🔧 工具名）
- 提供启动/停止/重启控制按钮
- AI 对话中可以直接调用该服务器的工具

---

## 5. 卸载流程

用户点击「卸载」按钮时，`uninstallMCPFromMarket(item_id, cmd)` 执行：

```
┌────────────────────────────────────────────────────────────────────┐
│  ① 停止服务                                                          │
│     mgr.unregister_client(item_id)                                  │
│     ├─ 清理子进程 / 断开远程连接                                      │
│     └─ 日志: 🛑 服务已停止                                           │
│                    ▼                                                 │
│  ② 删除配置                                                          │
│     mgr.remove_remote_server(item_id)                               │
│     └─ 从 mcp_servers.json 移除该服务器配置                          │
│                    ▼                                                 │
│  ③ 删除项目目录                                                      │
│     ├─ 从配置读取 githubRepoUrl → 计算目录名                          │
│     └─ shutil.rmtree(tools/mcp/server/{目录名})                     │
│                    ▼                                                 │
│  ④ 更新数据库                                                        │
│     db_item["installed"] = False → repo.upsert(db_item)             │
│                    ▼                                                 │
│  ⑤ 前端刷新                                                          │
│     mcpFinishInstall(item_id, 0) + loadMCPServers()                 │
└────────────────────────────────────────────────────────────────────┘
```

---

## 6. 配置文件说明 — `user_config/defaults/mcp_servers.json`

```json
{
  "mcpServers": {
    "server-id": {
      "transport": "stdio",
      "enabled": true,
      "auto_start": true,
      "name": "显示名称",
      "description": "服务器描述",
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "E:/.../tools/mcp/server/repo-name",
      "env": { "API_KEY": "环境变量" },
      "githubRepoUrl": "https://github.com/...（从市场安装时自动填充）"
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `transport` | string | ✓ | `stdio`（本地子进程）或 `http`（远程服务） |
| `enabled` | bool | | 是否启用，`false` 时不会自动启动 |
| `auto_start` | bool | | 是否随应用自动启动 |
| `command` | string | stdio 必填 | 启动命令（如 `node`、`python`、`npx`） |
| `args` | array | | 命令行参数（如 `["-m", "mcp_server"]`、`["dist/index.js"]`） |
| `cwd` | string | | 工作目录，相对路径自动转为绝对路径 |
| `env` | object | | 传递给子进程的环境变量 |
| `url` | string | http 必填 | 远程服务端点 URL |
| `name` / `description` | string | | 展示信息 |
| `githubRepoUrl` | string | | 来源 GitHub 仓库（市场安装自动填充） |

**系统命令白名单**（不进行路径解析）：`node`, `npx`, `npm`, `yarn`, `pnpm`, `uv`, `python`, `python3`, `pip`, `pip3`

---

## 7. 关键接口清单

### 市场管理（前端调用 Bridge）

| 方法 | 说明 |
|------|------|
| `getMCPMarket()` | 获取市场列表（优先本地数据库） |
| `refreshMCPMarket()` | 从 GitHub 刷新市场数据 |
| `installMCPFromMarket(item_id, repo_url)` | 从市场安装（clone + AI 分析） |
| `uninstallMCPFromMarket(item_id, cmd)` | 卸载（停止 + 删配置 + 删目录） |
| `refreshMarketFromUrl(url)` | 从任意 URL 抓取市场卡片 |

### AI 安装助手工具（AI 调用）

| 工具/方法 | 说明 |
|------|------|
| `directory_ops(Readdir)` | 列出服务器目录文件（AI 流程第 1 步） |
| `file_ops(Open)` | 读取服务器文件内容（AI 流程第 2 步） |
| `execute_system_command` | 在服务器目录执行安装依赖命令（AI 流程第 3 步） |
| `mcp_env_setup(server_id)` | 请求 API Key → 触发前端弹窗（AI 流程第 4 步） |
| `mcp_finalize_install(config_json)` | 完成安装：写配置 + 启动（AI 流程第 5 步） |
| `confirmEnvVars(server_id, env_json)` | 用户确认环境变量后的回调保存 |
| `listServerFiles(server_id)` | 列出服务器目录文件（桥接方法，供 AI 底层调用） |
| `readServerFile(server_id, filename)` | 读取服务器文件内容（桥接方法，供 AI 底层调用） |

### 服务器管理（市场卡片上的控制按钮）

| 方法 | 说明 |
|------|------|
| `startMCPServer(server_id)` | 启动服务器 |
| `stopMCPServer(server_id)` | 停止服务器 |
| `restartMCPServer(server_id)` | 重启服务器 |
| `getMCPServers()` | 获取所有服务器列表（含 online 状态、工具数） |
| `getMCPLog(item_id)` | 获取安装日志 |

---

## 8. 异常与边界处理

| 场景 | 处理策略 |
|------|---------|
| **克隆失败** | 多级加速链自动切换（直连 → 用户镜像 → 内置镜像列表），全部失败输出诊断详情 |
| **目录已存在** | 跳过 git clone，直接进入 AI 分析步骤 |
| **网络不通/被墙** | 内置 4 个 GitHub 加速镜像自动尝试，并可配置自定义镜像前缀 |
| **系统代理** | 自动检测 HTTPS_PROXY / HTTP_PROXY 环境变量并传给 git 使用 |
| **安装依赖超时** | 超时（180 秒）强制终止并重试 1 次 |
| **未找到仓库 URL** | 提示 ❌ 未找到 GitHub 仓库 URL，安装结束 |
| **API Key 缺失** | 触发前端弹窗 → 用户输入后保存 → AI 继续安装 |
| **环境变量优先级** | 用户确认的 env 始终覆盖 AI 传入的同名变量 |
| **安装上下文丢失** | 提示 ❌ 安装上下文丢失，安装失败 |
| **启动失败** | 记录日志，`register_client` 返回 false → 前端提示 |
| **子进程崩溃** | `MCPLocalClient.call_tool()` 检测到进程退出时自动重启并重试 |
| **HTTP 401 未认证** | 触发回调 → 前端弹出 API Key 输入框 → 重试 |
| **工具执行超时** | `MCPDispatcher` 默认 60 秒超时，返回 ❌ 执行超时 |
| **Windows 命令兼容** | 自动解析 `npx`/`.cmd`/`.bat`，PATH 自动补充 node/npm/python 目录 |
| **事件循环冲突** | 子进程绑定独立事件循环，同步调用通过线程池执行，避免阻塞 AI 异步循环 |
| **后台并发安全** | 遍历 `_clients` 前先快照，避免字典在加载线程中并发修改 |

---

## 9. 相关文件索引

| 文件 | 职责 |
|------|------|
| `view/js/mcp-market.js` | 前端市场列表渲染、搜索/分类筛选、安装/卸载交互 |
| `view/js/mcp-shared.js` | 日志推送、状态刷新、API Key 弹窗、服务器启停、AI 安装助手引导 |
| `bridge/mcp_bridge.py` | 后端核心：市场管理、安装/卸载、AI 安装助手、工具注册 |
| `tools/mcp/host.py` | MCPHost 单例：客户端生命周期管理、工具汇总、路由 |
| `tools/mcp/local_client.py` | stdio 子进程管理（JSON-RPC 通信） |
| `tools/mcp/http_client.py` | HTTP/SSE 远程连接（API Key 认证） |
| `tools/mcp/protocols/` | JSON-RPC 消息构建与解析 |
| `ai/mcp_dispatcher.py` | AI 工具调用路由（优先注册处理器，回退 MCPHost 路由） |
| `storage/repositories/mcp_market_repo.py` | mcp_market 表 CRUD 操作（含 server_id 字段） |
| `storage/repositories/mcp_server_logs_repo.py` | mcp_server_logs 表 CRUD 操作（含 market_id 字段） |
| `user_config/defaults/mcp_servers.json` | MCP 服务器配置存储 |
| `controller/mcp_controller.py` | 兼容层，转发到 MCPBridge |
| `skills/md/mcp-server-install/SKILL.md` | 内置 MD 技能：5 步 MCP 服务器安装流程指南 |
| `skills/md/mcp-server-install/references/config-templates.md` | 内置技能参考：npx / pip / uvx / node / HTTP 配置模板 |
| `skills/manager.py` | 技能管理器（含 PROTECTED_MD_SKILLS 内置保护名单） |
| `docs/mcp_flow.md` | MCP 整体业务流程文档（含本流程的简要版） |

---

## 10. 内置安装技能说明

系统内置 **`mcp-server-install`** 技能（MD Skill），为 AI 提供标准化的 MCP 服务器安装流程指导。

### 技能角色

- **技能（SKILL.md）**：操作指南 — 告诉 AI"怎么做"（5 步流程）
- **工具（mcp_env_setup / mcp_finalize_install）**：执行接口 — AI 实际调用的"手脚"

技能文档中明确声明了两个配套执行工具：

| 工具 | 作用 | 使用时机 |
|------|------|---------|
| `mcp_env_setup(server_id, env_vars)` | 弹出环境变量输入框，让用户填写 API Key 等密钥 | 第 4 步：需要环境变量时 |
| `mcp_finalize_install(item_id, config_json, extra_info)` | 提交最终配置 JSON，写入 mcp_servers.json 并启动服务 | 第 5 步：完成分析后 |

### 内置保护

- `mcp-server-install` 属于 **`PROTECTED_MD_SKILLS`** 保护名单
- UI 上**不显示删除按钮**（前端 `skills.js` 通过 `s.protected` 判断）
- 后端 `remove_md_skill()` **强制拒绝删除**（即使绕过 UI）
- 上传 MD 技能时**重名校验**：与内置保护名或已存在技能重名均被拒绝（前后端双重拦截）

### 前端引导

`startMCPInstallAnalysis()` 会向 AI 发送简短引导消息：

> 请遵循内置技能 **mcp-server-install** 完成该 MCP 服务器的分析、环境变量配置与配置提交。
> 按技能文档中的 5 步流程执行，最终只输出配置 JSON。

完整 5 步流程仅维护在 `SKILL.md` 一处（单一信息源），避免前端与技能文档不一致。
