# Tool 内建工具系统 — 业务流程文档

> 本文档基于 `tools/` 模块、`ai/tool_dispatcher.py`、`bridge/tool_bridge.py`、`controller/app_controller.py` 的实际实现编写，覆盖内建工具系统的**加载注册、启用管理、AI 工具调用、执行安全、前后端交互**等核心业务流程。

---

## 目录

- [1. 系统整体业务流程](#1-系统整体业务流程)
- [2. 内建工具清单](#2-内建工具清单)
- [3. 工具系统结构](#3-工具系统结构)
- [4. 工具加载与注册流程](#4-工具加载与注册流程)
- [5. 工具启用管理流程](#5-工具启用管理流程)
- [6. AI 工具调用执行流程](#6-ai-工具调用执行流程)
- [7. 工具执行安全机制](#7-工具执行安全机制)
- [8. 异常处理与错误码](#8-异常处理与错误码)

---

## 1. 系统整体业务流程

展示 AI 对话中内建工具的**发现 → 调用 → 执行 → 返回**完整链路。

```
用户输入消息 → AI 客户端 → LLM 返回 tool_call
                              │
                              ▼
                    ToolDispatcher.execute()
                              │
                    ┌─────────┴─────────┐
                    │                   │
            BuiltinManager        MCPHost（MCP 工具，见 mcp_flow.md）
            （内建工具优先）            
                    │
                    ├─ 工具已启用？ ──否──► 返回: ⚠️ 工具 'xxx' 未启用
                    │是
                    ├─ 工具已注册？ ──否──► 返回: ⚠️ 工具 'xxx' 未实现处理器
                    │是
                    ▼
            执行处理器（exec_xxx / xxx）
                    │
                    ├─ 成功 → 返回结果字符串 → AI 继续生成回复
                    ├─ 失败 → 返回 ❌ 错误信息
                    └─ 超时 → 返回 ❌ 执行超时
```

**双通道执行**：

| 通道 | 调度器 | 说明 |
|------|--------|------|
| 内建工具 | `ToolDispatcher` → `BuiltinManager` | 本地 Python 函数，通过 `builtin_tools_config.json` 控制启用 |
| MCP 工具 | `MCPDispatcher` → `MCPHost` → 客户端 | 外部 MCP 服务器工具（见 `mcp_flow.md`） |

---

## 2. 内建工具清单

内建工具位于 `tools/builtin/functions/*.py`，每个文件声明 `TOOLS` 列表（OpenAI function-call 格式）和对应的处理函数（`exec_<name>` 或 `<name>`）。

### 已启用工具（默认配置 `builtin_tools_config.json`）

| 工具名 | 功能 | 处理函数 |
|--------|------|---------|
| `run_command` | 执行 Shell 命令（git clone、npm install 等），支持超时 kill | `run_command()` |
| `github_get_issue` | 获取 GitHub Issue 详情 | `github_get_issue()` |
| `get_weather` | 查询天气 | `get_weather()` |
| `current_time` | 获取当前时间 | `current_time()` |
| `calculate` | 数学计算 | `calculate()` |
| `directory_ops` | 目录操作（Readdir/Mkdir/Rmdir/Chdir） | `directory_ops()` |
| `file_ops` | 文件操作（Create/Delete/Copy/Read/Write/Open/Close/Rename/Truncate） | `file_ops()` |
| `mcp_finalize_install` | 完成 MCP 服务器安装（写配置 + 启动） | `mcp_finalize_install()` |
| `mcp_env_setup` | MCP 环境变量设置（触发 API Key 弹窗） | `mcp_env_setup()` |

### 全部可用工具（20 个）

| 工具文件 | 工具名 | 功能 |
|---------|--------|------|
| `calculate.py` | `calculate` | 数学计算 |
| `current_time.py` | `current_time` | 当前时间 |
| `data_validator.py` | `data_validator` | 数据校验 |
| `db_query.py` | `db_query` | 数据库查询 |
| `directory_ops.py` | `directory_ops` | 目录操作 |
| `docker_ps.py` | `docker_ps` | Docker 容器列表 |
| `file_ops.py` | `file_ops` | 文件操作 |
| `get_weather.py` | `get_weather` | 天气查询 |
| `github_get_issue.py` | `github_get_issue` | GitHub Issue 查询 |
| `github_search_repos.py` | `github_search_repos` | GitHub 仓库搜索 |
| `hash_tool.py` | `hash_tool` | 哈希计算 |
| `mcp_env_setup.py` | `mcp_env_setup` | MCP 环境变量设置 |
| `mcp_server_install.py` | `mcp_finalize_install` | MCP 安装完成 |
| `network_checker.py` | `network_checker` | 网络连通性检测 |
| `run_command.py` | `run_command` | Shell 命令执行 |
| `string_processor.py` | `string_processor` | 字符串处理 |
| `system_inspector.py` | `system_inspector` | 系统信息检查 |
| `time_helper.py` | `time_helper` | 时间工具 |
| `web_search.py` | `web_search` | 网络搜索 |

---

## 3. 工具系统结构

```
┌────────────────────────────────────────────────────────────────┐
│                        前端 UI 层                                │
│   工具面板（tools.js）: 工具列表渲染、启停开关切换                 │
└────────────────────────┬───────────────────────────────────────┘
                         │ QWebChannel (pyqtSlot)
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                Bridge 层 (bridge/tool_bridge.py)                 │
│   ► getTools(): 动态加载 functions/ 目录 → 返回工具列表 JSON      │
│   ► toggleTool(): 切换工具启用/禁用状态（写入配置文件）            │
│   ► listUtilityTools(): 列出 utility 工具                        │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│      ToolManager (tools/manager.py) — 单例，内建 + MCP 整合       │
│   ┌────────────────────────────────────────────────────────┐   │
│   │ BuiltinManager (tools/builtin/builtin_tools_manager.py) │   │
│   │   ► 扫描 functions/ 目录                                  │   │
│   │   ► 读取 enabled_tools 配置                              │   │
│   │   ► 动态导入模块，注册 exec_<name> 处理器                  │   │
│   │   ► execute_tool() 执行（先校验启用状态）                  │   │
│   └────────────────────────────────────────────────────────┘   │
│   ┌────────────────────────────────────────────────────────┐   │
│   │ MCPHost (tools/mcp/host.py) — MCP 工具管理               │   │
│   │   （详见 docs/mcp_flow.md）                              │   │
│   └────────────────────────────────────────────────────────┘   │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│       AI 调度层 (ai/tool_dispatcher.py — ToolDispatcher)         │
│   ► 注册内建工具处理器（异步包装，同步函数在线程池执行）            │
│   ► 默认 30 秒超时                                               │
│   ► execute_batch(): 批量并发执行                                │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│       支撑组件：ToolRegistry / ToolExecutor / ToolValidator      │
│                  / ToolSandbox / Cache                          │
└────────────────────────────────────────────────────────────────┘
```

**组件职责：**

| 组件 | 文件 | 职责 |
|------|------|------|
| `ToolManager` | `tools/manager.py` | 单例门面：整合内建工具 + MCP 工具，提供统一 `get_tools()` / `execute_tool()` |
| `BuiltinManager` | `tools/builtin/builtin_tools_manager.py` | 内建工具加载器/执行器：扫描目录、读配置、注册处理器 |
| `ToolRegistry` | `tools/registry.py` | 单例注册中心：工具名 → 处理器映射，OpenAI 格式转换 |
| `ToolExecutor` | `tools/executor.py` | 异步执行器：`asyncio.wait_for` 超时控制（默认 30s），同步/异步兼容 |
| `ToolValidator` | `tools/validator.py` | 参数验证：JSON Schema 校验、类型强转、未定义字段清理 |
| `ToolSandbox` | `tools/sandbox.py` | 安全沙箱：Python 代码 AST 白名单检查 + 子进程隔离执行 |
| `ToolDispatcher` | `ai/tool_dispatcher.py` | AI 工具调度：LLM tool_call → 找到处理器 → 异步执行 |
| `ToolBridge` | `bridge/tool_bridge.py` | 前后端桥接：工具列表加载、启停开关、配置管理 |
| `Cache` | `tools/cache.py` | 工具调用结果缓存 |
| `Controller` | `controller/tool_controller.py` | 控制器层（兼容转发） |

---

## 4. 工具加载与注册流程

### 4.1 前端工具列表加载（ToolBridge.getTools）

```
ToolBridge.getTools()
    │
    ▼
_load_builtin_tools()
    ├─ 扫描 tools/builtin/functions/*.py（跳过 _ 开头）
    ├─ 动态 importlib 加载每个模块
    ├─ 读取模块的 TOOLS 列表（OpenAI function 格式）
    ├─ 解析 display 字段（中文名/描述/图标）
    ├─ 检查工具是否在 enabled_tools 配置中（返回 enabled 状态）
    └─ 清理配置：移除已不存在的工具名（保持一致）
    │
    ▼
返回 [{name, description, name_cn, description_cn, icon, category, enabled, parameters_info}]
```

### 4.2 AI 工具注册（BuiltinManager.get_tools_for_api）

```
get_tools_for_api()
    │
    ▼
_read_config() 读取 enabled_tools 列表
    │
    ├─ 空 → 返回 []，不传递工具给 AI
    │
    ▼
遍历 functions/ 目录，动态导入每个模块
    │
    ▼
读取模块 TOOLS 列表，筛选 name ∈ enabled_tools
    │
    ▼
注册处理器: exec_<name> 或 <name>（兼容两种命名）
    │
    ▼
返回已启用工具的 OpenAI 定义列表 → 注入 AI 请求
```

### 4.3 整体注册关系

```
Controller/ToolBridge ──► BuiltinManager ──► functions/*.py（TOOLS + 处理函数）
       │                        │
       │                        ▼
       │             ToolRegistry（单例注册中心）
       │                        │
       ▼                        ▼
 ToolDispatcher ◄──── ToolManager.get_tools()（内建 + MCP 合并）
```

---

## 5. 工具启用管理流程

配置存储：`user_config/defaults/builtin_tools_config.json`

```json
{
  "enabled_tools": [
    "run_command",
    "github_get_issue",
    "get_weather",
    "current_time",
    "calculate",
    "directory_ops",
    "file_ops",
    "mcp_finalize_install",
    "mcp_env_setup"
  ]
}
```

```
用户在前端工具面板切换开关
    │
    ▼
ToolBridge.toggleTool(name, enabled)
    │
    ├─ enabled = true  → 添加到 enabled_tools 列表
    └─ enabled = false → 从列表移除
    │
    ▼
写入 builtin_tools_config.json
    │
    ▼
返回 true → 前端刷新工具列表并推送最新状态
```

**启用状态的影响：**

| 场景 | 行为 |
|------|------|
| 工具未启用 | `execute_tool` 直接返回 `⚠️ 工具 'xxx' 未启用，请在工具面板中启用后使用` |
| 工具已启用未加载 | 懒加载：`if not self._tool_handlers: self.get_tools_for_api()` |
| 配置变更 | 前端 `toggleTool` 写入配置，下次 AI 请求时 `get_tools_for_api` 重新读取生效 |

---

## 6. AI 工具调用执行流程

### 6.1 单工具调用

```
LLM 返回 tool_call (function: run_command)
    │
    ▼
ToolDispatcher.execute(tool_name, arguments)
    │
    ├─ 未注册 → 返回: ⚠️ 内建工具 'xxx' 未注册处理器
    │
    ▼
找到处理器 → asyncio.wait_for(handler(args), timeout=30s)
    │
    ├─ 同步函数 → 自动在线程池执行（run_in_executor），避免阻塞事件循环
    ├─ 异步函数 → 直接 await
    │
    ├─ 超时 → 返回: ❌ 内建工具 'xxx' 执行超时（30s）
    ├─ 异常 → traceback 打印 + 返回: ❌ 内建工具 'xxx' 执行失败: {error}
    └─ 成功 → 返回结果字符串
```

### 6.2 执行链（以 run_command 为例）

```
ToolDispatcher.execute("run_command", {command: "git clone ...", cwd: "..."})
    │
    ▼
BuiltinManager.execute_tool("run_command", args)
    │
    ├─ 校验 enabled_tools 包含 "run_command"？否 → 返回未启用提示
    ├─ _tool_handlers 为空 → 懒加载 get_tools_for_api()
    │
    ▼
handler = run_command(args)
    │
    ▼
subprocess.Popen(shell=True, stdout=PIPE, stderr=STDOUT, text=True)
    │
    ▼
_read_output(): 行读取 + 实时输出 + 超时 kill（默认 60s，最大 300s）
    │
    ├─ returncode == 0 → "✅ 命令执行成功 (code=0):\n{output}"
    └─ returncode != 0 → "⚠️ 命令返回 code={code}:\n{output}"
```

### 6.3 批量执行

`ToolDispatcher.execute_batch(calls)`：使用 `asyncio.gather` 并发执行多个工具调用，返回结果列表。

---

## 7. 工具执行安全机制

### 7.1 参数验证（ToolValidator）

| 校验项 | 说明 |
|--------|------|
| 必填字段检查 | 遍历 schema.required，缺失报错 `缺少必填参数: {field}` |
| 类型检查 | string/integer/number/boolean/array/object 类型严格匹配 |
| 枚举值检查 | enum 字段值必须在允许范围内 |
| 参数清理 | `sanitize_args` 移除未在 schema 中定义的字段 |
| 类型强转 | `coerce_types` 将字符串整型/数字自动转为 int/float |

### 7.2 沙箱执行（ToolSandbox）

```python
ALLOWED_MODULES = {
    "json", "math", "random", "datetime", "re", "collections",
    "itertools", "functools", "typing", "enum", "string",
}
```

- **AST 扫描**：解析代码 AST，检查所有 import 是否在白名单中
- **子进程隔离**：代码在独立 Python 子进程中执行（`subprocess.run`）
- **超时保护**：默认 10 秒，超时返回 `执行超时`
- **临时文件清理**：执行完毕自动删除临时 .py 文件

### 7.3 命令执行安全（run_command）

- **超时限制**：默认 60 秒，最大 300 秒，超时强制 `process.kill()`
- **实时输出**：行读取模式（支持 `\r` 进度条），避免 Windows 管道阻塞
- **输出截断**：返回内容限制 4000 字符

---

## 8. 异常处理与错误码

| 异常场景 | 检测点 | 返回值 |
|---------|--------|--------|
| 工具未启用 | `BuiltinManager.execute_tool` 入口 | `⚠️ 工具 'xxx' 未启用，请在工具面板中启用后使用` |
| 工具未注册处理器 | `ToolDispatcher.execute` | `⚠️ 内建工具 'xxx' 未注册处理器` |
| 工具处理器不存在 | `BuiltinManager.execute_tool` | `⚠️ 工具 'xxx' 未实现处理器` |
| 执行超时 | `ToolDispatcher.execute`（30s） | `❌ 内建工具 'xxx' 执行超时（30s）` |
| 执行异常 | `ToolDispatcher.execute` 捕获 Exception | `❌ 内建工具 'xxx' 执行失败: {error}` |
| 命令未提供 | `run_command` | `❌ 请提供要执行的命令` |
| 命令执行失败 | `run_command` returncode != 0 | `⚠️ 命令返回 code={code}: {output}` |
| 命令执行超时 | `run_command` 超时 kill | `⏱️ 命令执行超时 ({timeout}秒)，已强制终止` |
| 沙箱模块越权 | `ToolSandbox` AST 检查 | `不允许导入模块: {module}` |
| 沙箱语法错误 | `ToolSandbox` AST 解析 | `语法错误: {error}` |

---

## 附：核心类速查

| 类 | 所在文件 | 职责 |
|----|---------|------|
| `ToolManager` | `tools/manager.py` | 单例门面：整合内建 + MCP 工具 |
| `BuiltinManager` | `tools/builtin/builtin_tools_manager.py` | 内建工具扫描/加载/执行 |
| `ToolRegistry` | `tools/registry.py` | 单例注册中心 |
| `ToolExecutor` | `tools/executor.py` | 异步执行器（30s 超时） |
| `ToolValidator` | `tools/validator.py` | 参数验证与类型转换 |
| `ToolSandbox` | `tools/sandbox.py` | 安全沙箱执行 |
| `ToolDispatcher` | `ai/tool_dispatcher.py` | AI 工具调度（异步执行 + 批量） |
| `ToolBridge` | `bridge/tool_bridge.py` | 前后端桥接（列表/开关/配置） |

---

*文档生成日期：2026-08-01 · 基于当前代码库实现编写。若模块逻辑变更，请同步更新本文档。*