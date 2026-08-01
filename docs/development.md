# Agent - 开发指南

## 环境准备

### 系统要求

- Python 3.10+
- PyQt5 (Windows: `pip install PyQt5`；Linux: `sudo apt install python3-pyqt5`)
- Node.js (可选，用于 MCP 服务器)

### 克隆并安装

```bash
git clone <repo-url>
cd agent

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 安装依赖
pip install -e .

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等配置
```

---

## 项目结构

```
agent/
├── ai/            # AI 层 - LLM 客户端、会话、提供商
│   └── providers/ # 模型提供商适配
├── api/           # API 层 - HTTP/WebSocket 接口
├── billing/       # 计费模块
├── config/        # 配置管理
├── core/          # 核心层 - Agent、生命周期、事件总线
├── data/          # 数据层 - 数据库、模型、仓储
│   ├── models/     # 数据模型
│   └── repositories/ # 数据访问层
├── docs/          # 文档
├── frontend/      # 前端资源
│   ├── css/       # 样式文件
│   ├── html/      # HTML 片段
│   └── js/        # JavaScript 文件
├── logs/          # 日志
├── plugins/       # 插件系统
├── scripts/       # 工具脚本
├── skills/        # 技能系统
│   ├── builtin/   # 内置技能
│   ├── md/        # Markdown 技能
│   └── triggers/  # 技能触发器
├── tests/         # 测试
├── tools/         # 工具系统
│   ├── builtin/   # 内置工具
│   └── mcp/       # MCP 工具
├── ui/            # UI 层
│   ├── bridges/   # Python↔JS 桥接
│   ├── template/  # HTML 模板 (生成)
│   └── themes/    # 主题配置
└── utils/         # 工具函数
```

---

## 开发工作流

### 前端开发

前端资源位于 `frontend/` 目录，编辑后运行生成模板：

```bash
python ui/gen_template.py
```

这将从 `frontend/css/`、`frontend/js/`、`frontend/html/` 读取资源，合并生成 `ui/template/main_layout.html`。

**CSS 加载顺序** (按依赖):
variables → base → sidebar → header → chat → input → panel → components → about → toast → responsive

**JS 加载顺序** (按依赖):
state → utils → panel → models → mcp → settings → tools → sidebar → chat

**添加新 CSS/JS 文件**: 编辑 `ui/gen_template.py` 中的 `css_files` / `js_files` 列表。

### 添加新桥接

1. 在 `ui/bridges/` 下创建桥接类，继承 `PluginBridge`
2. 使用 `@pyqtSlot` 装饰器暴露方法给前端
3. 在 `ui/bridges/__init__.py` 中导出
4. 在 `ui/web_view.py` 中注册桥接对象

### 添加新技能

1. 在 `skills/builtin/` 下创建技能类，继承 `BaseSkill`
2. 实现 `execute()` 方法
3. 技能自动注册到技能管理器

### 添加新插件

1. 在 `plugins/builtin/` 下创建插件类，继承 `PluginBase`
2. 实现 `on_load()`、`on_unload()` 等钩子方法
3. 插件自动被插件管理器发现加载

### 添加新工具

1. 在 `tools/builtin/` 下创建工具实现
2. 在 `tools/builtin/data.py` 中注册工具定义
3. 工具自动注册到工具调度器

---

## MCP 服务器开发

MCP 服务器通过标准 I/O 或 HTTP 与 Agent 通信。

### 本地 MCP 服务器

在 `tools/mcp_server/` 下创建服务器，使用 `mcp` Python SDK：

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("my-server")

@server.tool()
def my_tool(param: str) -> str:
    return f"处理: {param}"

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.run(stdio_server()))
```

---

## 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/unit/test_agent.py

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 带覆盖率
pytest --cov=.
```

### 编写测试

- 单元测试放在 `tests/unit/`
- 集成测试放在 `tests/integration/`
- 测试夹具放在 `tests/fixtures/`

---

## 提交规范

使用 Conventional Commits 格式：

```
feat: 新功能
fix: 修复
docs: 文档
refactor: 重构
test: 测试
chore: 杂项
style: 样式
perf: 性能
```

---

## 构建与发布

```bash
# 构建 Python 包
pip install build
python -m build

# Docker 构建
docker build -t agent .
docker-compose up -d