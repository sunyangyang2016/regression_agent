# regression Agent

基于 **PyQt5 + QWebEngine** 的 AI 智能对话桌面应用，集成大语言模型、MCP 工具调用、技能/插件扩展等能力。

## ✨ 核心特性

- 🤖 **多模型支持** — OpenAI、DeepSeek、Anthropic、Ollama 等模型提供商
- 🔌 **MCP 市场** — 浏览、搜索、安装/卸载 MCP 服务器
- 🧩 **工具系统** — 内置工具注册、沙箱执行、MCP 工具动态注入
- 📚 **技能系统** — Markdown 技能、触发器引擎、内置技能库
- 🧩 **插件系统** — 插件加载、钩子机制、依赖解析与安全校验
- 🎨 **现代化前端** — HTML/CSS/JS 原生渲染，深色主题
- 💬 **多会话管理** — 会话持久化、上下文管理、流式响应
- 🌐 **API 层** — RESTful HTTP + WebSocket，认证与限流

## 🚀 快速开始

### 环境要求

- Python 3.13+
- PyQt5
- Node.js（可选，用于部分 MCP 服务器）

### 安装与运行

```bash
git clone https://github.com/sunyangyang2016/regression_agent.git
cd regression_agent
pip install -e .
cp .env.example .env
python main.py
```

## 📁 项目结构

```
regression_agent/
├── ai/            # AI 层 - LLM 客户端、会话、提供商适配
├── api/           # API 层 - HTTP 路由、WebSocket、认证
├── bridge/        # 桥接层 - Python ↔ JS 通信
├── config/        # 配置管理
├── controller/    # 控制器层 - 各功能控制
├── core/          # 核心层 - Agent 主控、生命周期
├── data/          # 数据层 - 数据库、仓储
├── model/         # 数据模型与业务服务
├── plugins/       # 插件系统
├── skills/        # 技能系统
├── tools/         # 工具系统 - 注册、执行、MCP 工具
├── view/          # 前端资源 - HTML/CSS/JS
├── docs/          # 项目文档
├── tests/         # 测试
├── scripts/       # 工具脚本
└── main.py        # 应用入口
```

## 📚 文档

| 文档 | 说明 |
|------|------|
| [系统架构](docs/architecture.md) | 模块架构、通信流程、技术栈 |
| [开发指南](docs/development.md) | 环境搭建、开发工作流 |
| [API 参考](docs/api.md) | 接口定义与调用说明 |

## 🧪 测试

```bash
pytest
pytest tests/unit/
pytest tests/integration/
```

## 🤝 交流

欢迎交流与贡献！