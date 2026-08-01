# regression Agent - 开发指南

## 环境准备

### 系统要求

- Python 3.13+
- PyQt5 (Windows: `pip install PyQt5`；Linux: `sudo apt install python3-pyqt5`)
- Node.js (可选，用于部分 MCP 服务器)

### 克隆并安装

```bash
git clone https://github.com/sunyangyang2016/regression_agent.git
cd regression_agent
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
pip install -e .
cp .env.example .env
python main.py
```

---

## 项目结构

```
regression_agent/
├── main.py            # 应用入口
├── ai/                # AI 层
├── api/               # API 层
├── bridge/            # 桥接层
├── config/            # 配置管理
├── controller/        # 控制器层
├── core/              # 核心层
├── data/              # 数据层
├── model/             # 模型层
├── plugins/           # 插件系统
├── scripts/           # 工具脚本
├── skills/            # 技能系统
├── tools/             # 工具系统
├── view/              # 前端资源
├── tests/             # 测试
├── docs/              # 项目文档
└── user_config/       # 用户配置
```

---

## 开发工作流

### 添加新桥接

1. 在 `bridge/` 下创建桥接类，继承 `BridgeBase`
2. 使用 `@pyqtSlot` 装饰器暴露方法给前端
3. 在 `controller/bridge_loader.py` 中注册
4. 前端通过 `window.*bridge*.*method*()` 调用

### 添加新技能

1. 在 `skills/builtin/` 下创建技能类，继承 `BaseSkill`
2. 实现 `execute()` 方法
3. 声明 `name` / `description` / `input_schema`

### 添加新工具

1. 在 `tools/builtin/` 下创建工具实现
2. 注册到工具管理器
3. 自动注册到工具调度器

---

## 测试

```bash
pytest
pytest tests/unit/
pytest tests/integration/
```

---

## 提交规范

```
feat: 新功能
fix: 修复
docs: 文档
refactor: 重构
test: 测试
chore: 杂项
style: 样式
perf: 性能