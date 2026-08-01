# Regression Agent — 优化版项目架构

基于当前项目的经验总结，重新设计的模块化架构。

---

## 🏗️ 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Application Layer                       │
├─────────────────────────────────────────────────────────────────┤
│  main.py                                                        │
│  └── Agent (Facade)  ← 统一入口，协调各子系统                    │
├─────────────────────────────────────────────────────────────────┤
│                    Core Subsystems                               │
├───────────────┬───────────────┬────────────────┬───────────────┤
│  UI Layer     │  AI Layer     │  Tool Layer    │  Config Layer │
├───────────────┼───────────────┼────────────────┼───────────────┤
│ • MainWindow  │ • AIClient    │ • ToolManager  │ • ConfigMgr   │
│ • Bridge      │ • StreamHandler│ • BuiltinMgr  │ • ThemeMgr    │
│ • ChatManager │ • SessionMgr  │ • MCPManager   │ • EventBus    │
│ • WebEngine   │ • ContextMgr  │ • ToolExecutor │               │
└───────────────┴───────────────┴────────────────┴───────────────┘
```

---

## 📁 目录结构

```
agent/
├── main.py                          # 入口文件
│
├── core/                            # 核心模块
│   ├── __init__.py
│   ├── agent.py                     # Agent 主类（Facade）
│   ├── event_bus.py                 # 事件总线（解耦）
│   └── lifecycle.py                 # 生命周期管理
│
├── ui/                              # UI 层
│   ├── __init__.py
│   ├── main_window.py               # 主窗口逻辑
│   ├── bridges/                     # 前后端桥接
│   │   ├── __init__.py
│   │   ├── base_bridge.py           # 桥接基类
│   │   ├── main_bridge.py           # 主功能桥接
│   │   ├── config_bridge.py         # 配置桥接
│   │   └── tool_bridge.py           # 工具桥接
│   ├── chat_manager.py              # 对话管理
│   ├── web_view.py                  # Web视图封装
│   └── theme_manager.py             # 主题管理
│
├── ai/                              # AI 层
│   ├── __init__.py
│   ├── client.py                    # AI客户端（工厂模式）
│   ├── stream_handler.py            # 流式处理
│   ├── session_manager.py           # 会话管理
│   ├── context_manager.py           # 上下文管理
│   └── providers/                   # 多供应商支持
│       ├── __init__.py
│       ├── base_provider.py
│       ├── openai_provider.py
│       └── deepseek_provider.py
│
├── tools/                           # 工具层
│   ├── __init__.py
│   ├── manager.py                   # 工具管理器（统一接口）
│   ├── executor.py                  # 工具执行器
│   ├── builtin/                     # 内建工具
│   │   ├── __init__.py
│   │   ├── data.py                  # 工具定义
│   │   ├── loader.py                # 动态加载
│   │   └── weather.py               # 示例工具实现
│   ├── mcp/                         # MCP 工具
│   │   ├── __init__.py
│   │   └── mcp_manager.py
│   └── registry.py                  # 工具注册中心
│
├── config/                          # 配置层
│   ├── __init__.py
│   ├── manager.py                   # 配置管理器
│   ├── schema.py                    # 配置Schema
│   ├── defaults.py                  # 默认配置
│   └── validators.py                # 配置验证
│
├── data/                            # 数据层
│   ├── __init__.py
│   ├── repositories/               # 数据仓库
│   │   └── session_repo.py
│   └── serializers.py              # 序列化工具
│
├── utils/                           # 工具类
│   ├── __init__.py
│   ├── logger.py                   # 日志系统
│   ├── queue_manager.py            # 队列管理器
│   ├── async_utils.py              # 异步工具
│   └── qt_helpers.py               # Qt辅助函数
│
├── frontend/                        # 前端资源
│   ├── html/
│   │   └── main_layout.html
│   ├── css/
│   ├── js/
│   │   ├── app.js
│   │   ├── bridge.js
│   │   ├── builtin.js
│   │   └── utils.js
│   └── assets/
│
└── tests/                           # 测试
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## 🧩 各层职责

### `core/` — 核心层

| 文件 | 职责 |
|------|------|
| `agent.py` | Facade 模式，统一协调各子系统，管理初始化、启动、清理生命周期 |
| `event_bus.py` | 事件总线，模块间解耦通信，不再依赖 Qt Signal |
| `lifecycle.py` | 应用启动/停止流程管理，插件生命周期钩子 |

### `ui/` — UI 层

| 文件/模块 | 职责 |
|-----------|------|
| `main_window.py` | QMainWindow 创建、布局管理 |
| `bridges/` | 所有 `@pyqtSlot` 桥接方法集中管理 |
| `bridges/base_bridge.py` | 桥接基类，提供 `call_js()` 公共方法 |
| `bridges/main_bridge.py` | 主功能桥接（sendToAI, addMessage 等） |
| `bridges/config_bridge.py` | 配置相关桥接（saveConfig, getConfig） |
| `bridges/tool_bridge.py` | 工具相关桥接（getTools, toggleTool, listUtilityTools） |
| `chat_manager.py` | 对话消息管理、DOM 操作封装 |
| `web_view.py` | QWebEngineView 封装，模板加载、桥接初始化 |
| `theme_manager.py` | 主题管理 |

### `ai/` — AI 层

| 文件/模块 | 职责 |
|-----------|------|
| `client.py` | AI 客户端工厂，根据 provider 创建实例 |
| `stream_handler.py` | 流式响应处理，工具调用循环 |
| `session_manager.py` | 对话会话管理，消息历史维护 |
| `context_manager.py` | 上下文注入（技能、工具描述等） |
| `providers/` | 多供应商支持（OpenAI、DeepSeek 等） |

### `tools/` — 工具层

| 文件/模块 | 职责 |
|-----------|------|
| `manager.py` | 工具管理器，统一 `get_tools()` / `execute_tool()` 接口 |
| `executor.py` | 工具执行器，支持异步/同步执行、超时、重试 |
| `builtin/` | 内建工具（utility/ 目录的描述 + 实现） |
| `builtin/loader.py` | 从 utility/ 目录动态加载工具描述 |
| `mcp/` | MCP 协议工具管理 |
| `registry.py` | 工具注册中心，管理处理器映射 |

### `config/` — 配置层

| 文件 | 职责 |
|------|------|
| `manager.py` | 配置读写，YAML 持久化 |
| `schema.py` | 配置结构定义，类型校验 |
| `defaults.py` | 默认配置预设 |
| `validators.py` | 配置校验逻辑 |

### `data/` — 数据层

| 文件/模块 | 职责 |
|-----------|------|
| `repositories/session_repo.py` | 对话会话持久化 |
| `serializers.py` | 序列化/反序列化工具 |

### `utils/` — 工具层

| 文件 | 职责 |
|------|------|
| `logger.py` | 统一日志系统，分级日志输出 |
| `queue_manager.py` | 前端消息队列管理器 |
| `async_utils.py` | asyncio 工具函数 |
| `qt_helpers.py` | Qt 相关辅助函数 |

### `frontend/` — 前端资源

```
frontend/
├── js/
│   ├── app.js         # 主入口，渲染协调
│   ├── bridge.js      # JS ↔ Python 统一桥接层
│   ├── builtin.js     # 内建工具管理
│   └── utils.js       # 工具函数
├── css/               # 样式文件
├── html/              # HTML 模板
└── assets/            # 静态资源
```

---

---

## 🔄 数据流

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  用户操作  │───▶│ UI Layer │───▶│ 桥接层   │───▶│ 事件总线  │
└──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                      │
                                         ┌───────────┴────────────┐
                                         │                        │
                                    ┌────▼─────┐          ┌───────▼────┐
                                    │对话管理器 │          │  工具管理器  │
                                    └────┬─────┘          └───────┬────┘
                                         │                        │
                                    ┌────▼─────┐          ┌───────▼────┐
                                    │AI Client │          │  执行器    │
                                    └────┬─────┘          └───────┬────┘
                                         │                        │
                                         └──────────┬─────────────┘
                                                    │
                                               ┌────▼────┐
                                               │ API调用 │
                                               └─────────┘
```

### 各环节说明

| 环节 | 职责 | 对应文件 |
|------|------|----------|
| **用户操作** | 用户在 UI 上的交互（点击、输入） | `frontend/js/*` |
| **UI Layer** | 前端界面渲染、事件响应 | `frontend/` + `ui/main_window.py` |
| **桥接层** | JS ↔ Python 双向通信（QWebChannel） | `ui/bridges/*.py` + `frontend/js/bridge.js` |
| **事件总线** | 模块间解耦通信，分发事件 | `core/event_bus.py` |
| **对话管理器** | 聊天消息管理、上下文注入 | `ui/chat_manager.py` |
| **工具管理器** | 工具注册、加载、查询 | `tools/manager.py` + `tools/builtin/` + `tools/mcp/` |
| **AI Client** | AI API 调用封装、流式处理 | `ai/client.py` + `ai/stream_handler.py` |
| **执行器** | 工具调用执行、结果处理 | `tools/executor.py` |
| **API 调用** | 最终向 OpenAI / DeepSeek 发起请求 | `ai/providers/` |

### 详细数据流

#### 应用启动流程

```
main.py
  └── Agent()
      ├── core/lifecycle.py → 初始化各子系统
      ├── ui/main_window.py → 创建 QMainWindow + WebEngine
      ├── ui/bridges/*.py → 注册 QWebChannel 桥接对象
      ├── ui/web_view.py → 加载 HTML 模板
      └── ui/chat_manager.py → 连接 AI、同步状态、启动轮询
```

### 内建工具管理

```
frontend/js/tools.js → getTools() / toggleTool(name, enabled)
  └── QWebChannel → bridge/tool_bridge.py
       └── user_config/defaults/builtin_tools_config.json（enabled_tools 开关）
            └── tools/builtin/builtin_tools_manager.py（按开关加载 functions/*.py）
```

### AI 对话请求

```
frontend/js/app.js → __msgQueue.push()
  └── utils/queue_manager.py → 轮询取出
       └── ui/chat_manager.py
            ├── ai/context_manager.py → 注入工具+技能上下文
            ├── tools/manager.py → 获取已安装工具定义
            │   ├── tools/builtin/loader.py ← utility/*/description.json
            │   └── tools/mcp/mcp_manager.py
            └── ai/client.py → ai/stream_handler.py
                 └── OpenAI/DeepSeek API → 流式回复
```

---

## 📊 当前 vs 优化对比

| 方面 | 当前 | 优化后 |
|------|------|--------|
| **桥接管理** | 分散在多个文件 | 集中到 `ui/bridges/` 统一管理 |
| **工具管理** | `builtin_tools/` 和 `mcp/` 分离 | 统一到 `tools/` 层，统一接口 |
| **配置管理** | 散落在 `config/` | 加入 Schema 校验和验证器 |
| **数据持久化** | 直接文件读写 | 通过 Repository 模式 |
| **日志系统** | 散落的 `print()` | 统一的 `logger.py` |
| **AI 供应商** | 仅 DeepSeek | providers/ 支持多供应商 |
| **前端资源** | 在 `assets/` 下 | 整合到 `frontend/` |
| **工具定义** | `utility/` 目录描述 | `tools/builtin/loader.py` 加载 |