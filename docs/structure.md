# Regression Agent 项目结构

基于 PyQt5 + QWebEngine 的桌面 AI 代理应用。

---

## 📁 顶层目录

```
E:/workplace/agent/
├── main.py                  # 应用入口
├── core/                    # 核心模块（Agent, EventBus, Lifecycle）- 精简版
├── controller/              # ★ Controller 层 - 协调调度
│   ├── app_controller.py    # 应用主控制器
│   ├── bridge_manager.py    # 桥接管理器（生命周期检测）
│   ├── bridge_loader.py     # 桥接加载器（骨架注入 + setHtml）
│   └── chat_controller.py   # 聊天控制器
├── model/                   # ★ Model 层 - 数据与业务逻辑
│   ├── ai_model.py          # AI 模型（消息、连接、流式）
│   ├── conversation_model.py# 会话模型（CRUD、持久化）
│   └── state_manager.py     # 全局状态管理
├── bridge/                  # ★ Bridge 层 - WebChannel 通信通道
│   ├── main_bridge.py       # 主桥接（对话转发）
│   ├── config_bridge.py     # 配置桥接
│   ├── tool_bridge.py       # 工具桥接
│   └── skill_bridge.py      # 技能桥接
├── view/                    # ★ View 层 - 纯前端资源
│   ├── index.html           # 主入口 HTML
│   ├── css/                 # CSS 样式
│   ├── js/                  # JavaScript
│   │   └── bridge.js        # 前端桥接封装
│   └── html/                # HTML 片段
├── ui/                      # （保留兼容）UI 层（Window, Bridges, Theme）
│   ├── bridge_loader.py     # （旧版，迁移中）
│   ├── template/            # HTML 模板
│   └── bridges/             # QWebChannel 桥接对象（旧版，迁移中）
├── ai/                      # AI 层（Client, Stream, Providers）
│   └── providers/           # 多供应商（OpenAI, DeepSeek 等）
├── tools/                   # 工具层（Builtin, MCP, Executor）
│   ├── builtin/             # 内建工具
│   └── mcp/                 # MCP 协议管理
├── skills/                  # 技能系统（Manager, Loader, Triggers）
├── config/                  # 配置层（Schema, Validators）
├── data/                    # 数据层（Repositories, Models）
│   ├── models/              # ORM 模型
│   └── repositories/        # 数据仓库
├── frontend/                # 前端静态资源
│   ├── css/                 # CSS 样式
│   │   ├── main.css         # 主样式（从 main_layout.html 提取）
│   │   └── fontawesome.min.css  # Font Awesome（备用）
│   ├── html/                # HTML 片段
│   ├── js/                  # JavaScript
│   └── webfonts/            # 字体文件
├── plugins/                 # 插件系统
├── utils/                   # 工具类
├── api/                     # API 网关
├── billing/                 # 计费模块
├── logs/                    # 日志文件
├── tests/                   # 测试
├── scripts/                 # 构建脚本
├── docs/                    # 文档
│   ├── architecture.md      # 架构设计文档
│   ├── api.md               # API 文档
│   ├── development.md       # 开发指南
│   └── structure.md         # 本文档
├── user_config/             # 用户配置
│   └── defaults/            # 默认配置（JSON）
├── temp_html/               # 临时 HTML 目录
├── structure.md             # 本文件
├── pyproject.toml           # 项目配置
└── uv.lock                  # 依赖锁定
```

---

## 🔧 核心模块详解

### `main.py` — 应用入口

```python
main.py → from core.agent import Agent → Agent().run()
```

### `core/` — 核心模块

```
core/
├── agent.py           # Agent 主类
│                      # - create_main_window(): 创建 QMainWindow + QWebEngineView
│                      # - BridgeLoader.load(): 骨架 → setHtml → 桥接建立
│                      # - run(): 启动事件循环
│                      # - 先 window.show() 再 BridgeLoader.load()（关键修复）
│
├── event_bus.py       # 事件总线（Qt Signal 桥接）
├── lifecycle.py       # 生命周期管理
├── state_manager.py   # 状态管理器
├── constants.py       # 全局常量
└── plugin_base.py     # 插件基类
```

### `ui/` — UI 渲染层

```
ui/
├── bridge_loader.py   # ★ 核心：桥接加载器
│                      # 1. setHtml(骨架 ~2KB) → 渲染进程稳定
│                      # 2. @font-face 移除（防止字体阻塞）
│                      # 3. QTimer.singleShot(0) 确保信号不丢失
│
├── main_window.py     # 主窗口封装
├── chat_manager.py    # 聊天管理器
├── gen_template.py    # HTML 模板生成器
├── theme_manager.py   # 主题管理器
├── web_view.py        # WebView 封装
│
├── template/
│   └── main_layout.html  # 完整 UI 模板（CSS 全部内联）
│
└── bridges/           # QWebChannel 桥接对象
    ├── main_bridge.py    # "py_bridge" - 主要功能
    ├── config_bridge.py  # "config_bridge" - 配置同步
    ├── tool_bridge.py    # "tool_bridge" - 工具管理
    ├── skill_bridge.py   # "skill_bridge" - 技能管理
    └── plugin_bridge.py  # 插件桥接基类
```

### `ai/` — AI 交互模块

```
ai/
├── client.py              # AI 客户端
├── session_manager.py     # 会话管理
├── context_manager.py     # 上下文管理
├── prompt_builder.py      # 提示词构建
├── stream_handler.py      # 流式处理器
├── tool_dispatcher.py     # 工具调度器
├── token_counter.py       # Token 计数
├── cost_tracker.py        # 成本追踪
├── response_parser.py     # 响应解析
│
└── providers/             # 多供应商
    ├── base_provider.py   # 供应商基类
    ├── openai_provider.py # OpenAI
    ├── deepseek_provider.py # DeepSeek
    └── factory.py         # 供应商工厂
```

### `frontend/` — 前端静态资源

```
frontend/
├── css/
│   ├── main.css           # 主样式（36KB）
│   ├── fontawesome.min.css # Font Awesome（备用，99KB）
│   └── *.css              # 各模块独立样式
│
├── js/
│   ├── chat.js            # 对话管理
│   ├── sidebar.js         # 侧边栏
│   ├── tools.js           # 工具管理
│   ├── panel.js           # 面板管理
│   ├── settings.js        # 设置
│   └── *.js               # 其他功能脚本
│
├── html/                  # HTML 片段
│   └── *.html             # 各面板 HTML
│
└── webfonts/              # Font Awesome 字体文件
    ├── fa-brands-400.woff2
    ├── fa-regular-400.woff2
    ├── fa-solid-900.woff2
    └── fa-v4compatibility.woff2
```

### `tools/` — 工具层

```
tools/
├── manager.py         # 工具管理器
├── executor.py        # 工具执行器
├── registry.py        # 工具注册表
├── validator.py       # 工具验证
├── sandbox.py         # 沙箱执行
├── cache.py           # 工具缓存
│
├── builtin/           # 内建工具
│   ├── loader.py      # 内建工具加载器
│   └── data.py        # 内建工具数据
│
└── mcp/               # MCP 协议
    ├── mcp_manager.py # MCP 管理器
    └── host.py        # MCP Host（子进程）
```

### `skills/` — 技能系统

```
skills/
├── manager.py      # 技能管理器（QWebChannel 桥接）
├── base.py         # 技能基类
├── registry.py     # 技能注册表
├── loader.py       # 技能加载器
├── executor.py     # 技能执行器
├── validator.py    # 技能验证器
├── context.py      # 技能上下文
│
├── builtin/        # 内置技能（10+ 个）
├── custom/         # 自定义技能
├── triggers/       # 触发机制
└── ui/             # 技能 UI
```

### `config/` — 配置管理

```
config/
├── config_manager.py  # 配置管理器（YAML 读写）
├── config.yaml        # 运行时配置
├── defaults.py        # 默认值
├── schema.py          # 配置模式
├── validators.py      # 配置验证
├── env_manager.py     # 环境管理
├── secret_manager.py  # 密钥管理
├── migration.py       # 迁移工具
└── yaml_loader.py     # YAML 加载器
```

### `data/` — 数据层

```
data/
├── database.py        # 数据库连接（SQLite）
├── migrations.py      # 数据迁移
├── serializers.py     # 序列化器
├── models/            # ORM 模型
│   ├── base.py
│   ├── conversation.py
│   ├── message.py
│   ├── session.py
│   ├── tool.py
│   └── skill.py
└── repositories/      # 数据仓库
    ├── base_repository.py
    ├── conversation_repo.py
    └── message_repo.py
```

### `utils/` — 工具类

```
utils/
├── logger.py        # 日志
├── async_utils.py   # 异步工具
├── thread_pool.py   # 线程池
├── queue_manager.py # 队列管理
├── path_manager.py  # 路径管理
├── file_utils.py    # 文件工具
├── network_utils.py # 网络工具
├── crypto_utils.py  # 加密工具
├── string_utils.py  # 字符串工具
└── ...
```

---

## 🔄 应用启动流程（当前优化版）

```
python main.py
  │
  ├── Agent.run()
  │   ├── QApplication(sys.argv)
  │   ├── Agent.create_main_window()
  │   │   ├── QMainWindow + QWebEngineView
  │   │   ├── QWebEngineSettings 优化
  │   │   ├── QWebChannel 注册 4 个桥接对象
  │   │   │   ├── "py_bridge" → MainBridge
  │   │   │   ├── "config_bridge" → ConfigBridge
  │   │   │   ├── "tool_bridge" → ToolBridge
  │   │   │   └── "skill_bridge" → SkillManager
  │   │   ├── window.show()       ← ★ 先显示窗口
  │   │   └── BridgeLoader.load()  ← ★ 再加载 HTML
  │   │
  │   └── BridgeLoader 内部：
  │       1. setWebChannel(channel)
  │       2. 读取 main_layout.html（CSS 全部内联）
  │       3. 移除 @font-face（防止字体阻塞）
  │       4. 注入 qwc.js + 桥接脚本
  │       5. QTimer.singleShot(0, setHtml) ← 确保信号不丢失
  │       6. loadFinished → _on_finished()
  │       7. BridgeManager.check_bridge_ready() → 桥接检查
  │
  └── 桥接就绪后：
      ├── sync_config_to_js()     # 同步配置
      ├── sync_skills_to_js()     # 同步技能
      ├── sync_tools_to_js()      # 同步工具
      └── chat_manager.try_connect() # 连接 AI
```

## ⚠️ 已知问题与修复

| 问题 | 症状 | 修复 |
|------|------|------|
| `setHtml` 大 HTML 渲染进程退出 | HTML > 128KB 时卡死 | 骨架 ~2KB + 拆分注入 < 100KB |
| `runJavaScript` 超大字符串 IPC 崩溃 | > 128KB 字符串传递 | 拆分多次调用，每块 < 100KB |
| `loadFinished` 信号竞态 | load 完成后信号未收到 | `QTimer.singleShot(0)` 延迟 setHtml |
| 窗口未 show 时渲染进程未启动 | 卡在 loadProgress 70% | `window.show()` 先于 BridgeLoader.load() |
| Font Awesome `@font-face` 阻塞 | data: URL 无法加载 file:// 字体 | 移除 `@font-face`，图标变方块 |

---

## 📊 代码统计

| 类别 | 数量 |
|------|:----:|
| Python 文件 | ~80+ 个 |
| JavaScript 文件 | ~10 个 |
| CSS 文件 | ~10 个 |
| HTML 模板 | 1 个主模板 + ~10 个片段 |
| 内建工具 | 10 个 |
| 测试文件 | 5 个 |
| 总行数 | ~25000+ |