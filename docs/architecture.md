# regression Agent - 系统架构文档

## 概述

regression Agent 是一个基于 PyQt5 + QWebEngine 的 AI 智能对话桌面应用，集成大语言模型、MCP 工具调用、技能/插件扩展等能力。采用分层架构设计，通过 Controller 层协调调度、Bridge 层实现前后端通信、View 层渲染界面。

---

## 整体架构

```
┌─────────────────────────────────────────────────┐
│                    View 层 (view/)               │
│  ┌─────────────┐  ┌──────────┐  ┌────────────┐  │
│  │  index.html │  │  css/    │  │  js/       │  │
│  └──────┬──────┘  └────┬─────┘  └────┬───────┘  │
│         └──────────────┘             │           │
│              │ Bridge 通信 (QWebChannel)          │
│              ▼                                    │
│  ┌──────────────────────────────────────────┐    │
│  │         Bridge 层 (bridge/)              │    │
│  │  ChatBridge / ModelBridge / MCPBridge    │    │
│  │  SkillBridge / ToolBridge                │    │
│  └──────────────────────────────────────────┘    │
├─────────────────────────────────────────────────┤
│               Controller 层 (controller/)         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────┐ │
│  │ AppController│ │ BridgeManager│ │ Bridge   │ │
│  │ (主控制器)   │ │ (桥接管理)   │ │ Loader   │ │
│  └──────┬───────┘ └──────────────┘ └──────────┘ │
│         │                                         │
│         ▼                                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────┐ │
│  │ AIController │ │ ChatController│ │ MCPController│
│  └──────────────┘ └──────────────┘ └──────────┘ │
├─────────────────────────────────────────────────┤
│                    Core 层 (core/)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Agent    │ │ Lifecycle│ │ EventBus         │ │
│  │ (Facade) │ │ (生命周期)│ │ (事件总线)       │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────────────────────────────────────┐   │
│  │ StateManager / PathManager / PluginBase  │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│                    AI 层 (ai/)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Client   │ │ Session  │ │ Context          │ │
│  │ (客户端) │ │ (会话)   │ │ (上下文)         │ │
│  └────┬─────┘ └──────────┘ └──────────────────┘ │
│       │                                          │
│       ▼                                          │
│  ┌──────────────────────────────────────────┐    │
│  │  Dispatcher: Tool / Skill / MCP / Stream │    │
│  │  Providers: 多模型提供商                  │    │
│  └──────────────────────────────────────────┘    │
├─────────────────────────────────────────────────┤
│            工具/技能/插件层                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Tools    │ │ Skills   │ │ Plugins          │ │
│  │ (工具)   │ │ (技能)   │ │ (插件)           │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
├─────────────────────────────────────────────────┤
│                  数据/模型层                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Database │ │ Models   │ │ Repositories     │ │
│  │ (数据)   │ │ (模型)   │ │ (仓储)           │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
├─────────────────────────────────────────────────┤
│                   API 层 (api/)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Routes   │ │ WebSocket│ │ Auth/Gateway     │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## 模块职责

### View 层 (`view/`)
- **index.html**: 前端主入口页面
- **css/**: 样式文件（主题、布局、组件）
- **js/**: JavaScript 模块（聊天、MCP 市场、技能、工具、设置等）
- **html/**: HTML 片段模板

### Bridge 层 (`bridge/`)
- **base.py**: 桥接基类，提供 JS 执行能力
- **chat_bridge.py**: 聊天桥接（对话发送、消息处理）
- **model_bridge.py**: 模型桥接（模型列表、状态同步）
- **mcp_bridge.py**: MCP 桥接（MCP 市场、服务器生命周期管理）
- **skill_bridge.py**: 技能桥接（技能管理、MD 技能操作）
- **tool_bridge.py**: 工具桥接（工具列表、启停控制）

### Controller 层 (`controller/`)
- **app_controller.py**: 应用主控制器，协调各子系统初始化
- **bridge_loader.py**: 桥接加载器（注入 QWebChannel 对象）
- **bridge_manager.py**: 桥接管理器（注册、生命周期检测）
- **chat_controller.py**: 对话控制器（消息处理、AI 交互）
- **ai_controller.py**: AI 控制器（模型配置、流式响应）
- **mcp_controller.py**: MCP 控制器（服务器管理）
- **skill_controller.py**: 技能控制器
- **tool_controller.py**: 工具控制器
- **config_controller.py**: 配置控制器

### Core 层 (`core/`)
- **agent.py**: Agent 主类（Facade），统一入口协调各子系统
- **lifecycle.py**: 生命周期管理（启动→运行→关闭）
- **event_bus.py**: 事件总线，模块间解耦通信
- **state_manager.py**: 全局状态管理
- **path_manager.py**: 路径管理
- **constants.py**: 全局常量
- **plugin_base.py**: 插件基类

### AI 层 (`ai/`)
- **client.py**: LLM 客户端抽象，统一调用接口
- **session_manager.py**: 会话管理
- **context_manager.py**: 上下文管理
- **prompt_builder.py**: 提示词构建
- **stream_handler.py**: 流式响应处理
- **tool_dispatcher.py**: 工具调度器
- **skill_dispatcher.py**: 技能调度器（技能 → AI 工具）
- **mcp_dispatcher.py**: MCP 工具调度器
- **response_parser.py**: 响应解析
- **token_counter.py**: Token 计数
- **cost_tracker.py**: 成本追踪
- **protocol.py**: 通信协议定义
- **providers/**: 多模型提供商适配

### 工具/技能/插件层
- **Tools** (`tools/`): 工具注册、执行、沙箱、缓存
- **Skills** (`skills/`): 技能加载、触发器、执行、MD 技能
- **Plugins** (`plugins/`): 插件加载、钩子、依赖解析、安全

### 数据/模型层 (`data/` + `model/`)
- **data/database.py**: 数据库连接
- **data/mcp_db.py**: MCP 数据库管理
- **data/migrations.py**: 数据迁移
- **data/repositories/**: 数据访问仓储
- **model/entities/**: 实体模型
- **model/services/**: 业务服务

### API 层 (`api/`)
- RESTful HTTP API + WebSocket 实时通信
- 认证、限流、中间件

---

## 数据流

### 用户消息处理

```
用户输入 → View(JS) → Bridge(ChatBridge) → ChatController
    → AI Client.send() → LLM Provider
    → 流式响应 → ChatController → Bridge → View 渲染
```

### 工具调用

```
Agent → ToolDispatcher → ToolManager.execute()
    → 沙箱执行 → 结果返回 → Agent → AI 处理结果
```

### MCP 服务器安装

```
View(JS) → MCPBridge.installMCPFromMarket()
    → git clone → AI 安装助手分析 → finalizeMCPInstall
    → 写入配置 → 启动服务 → 回调 mcpFinishInstall → View 更新
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 桌面框架 | PyQt5 |
| Web 渲染 | QWebEngine |
| 前端 | HTML/CSS/JS (原生) |
| AI 模型 | OpenAI, DeepSeek, Anthropic, Ollama |
| 数据库 | SQLite |
| MCP | Model Context Protocol |
| 构建工具 | uv / pip |

---

## 启动流程

```
python main.py
  └── Agent.run()
      ├── QApplication + QWebEngine 初始化
      ├── AppController.initialize()
      │   ├── 初始化 AI 客户端
      │   ├── 初始化技能系统
      │   ├── 初始化工具系统
      │   ├── 初始化插件系统
      │   └── 初始化 MCP 系统
      ├── BridgeLoader.load()
      │   ├── 注册 5 个桥接对象
      │   ├── 加载 index.html
      │   └── BridgeManager 检查桥接就绪
      └── 桥接就绪后同步配置/技能/工具到前端