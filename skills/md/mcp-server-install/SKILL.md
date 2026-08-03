---
name: mcp-server-install
enabled: true
description: MCP 服务器安装助手 - 按 5 步标准流程完成 MCP 服务器分析与安装
---

# MCP Server Install Assistant

当从 MCP 市场安装服务器需要进行项目分析时，按以下 5 步流程执行。

## 输出行为规范

- 不要声明"我将按照某技能执行"之类的套话
- 每一步只需简洁说明当前正在做什么
- 中间步骤尽量精简，不需要解释每个动作的背景
- **只有最终一步**需要输出完整配置 JSON（见第 5 步格式）
- 全程保持简短、直接、可执行

## 第 1 步：浏览目录结构

- 浏览服务器的文件与子目录
- 目录跳过即可；普通文件可以读取；**不要读取日志文件**
- 如果只有日志文件没有源码，需要重新拉取代码，**不要删除源码目录**

## 第 2 步：阅读关键文件

- 打开并阅读项目的关键文件，以识别入口与启动方式
- 重点关注：`.mcp.json`、`package.json`、`pyproject.toml`、`README.md`、入口文件（如 `index.js`、`server.py`、`main.py`）
- 从 README 中确认启动方式（npx / pip / uvx / node）和所需的环境变量

## 第 3 步：安装依赖

- 有 `requirements.txt` → 安装 Python 依赖
- 有 `package.json` → 安装 npm 依赖
- 有 `pyproject.toml` → 以可编辑模式安装项目依赖
- 依赖已在环境中（已安装提示）时无需重复安装

## 第 4 步：环境变量（可选）

- 如需 API Key 等环境变量，**由系统自动检测并弹出配置窗口**，AI 无需处理
- 用户确认后环境变量自动保存到安装流程中
- 读取 `.env.example` / `.env.sample` 等文件时，`YOUR_XXX`、`<your_key>`、`changeme`、`placeholder`、连续 `xxx`/`XXXX` 等值均为**占位符，不代表真实密钥**，不得写入最终配置

## 第 5 步：输出最终配置 JSON

审阅系统生成的配置草稿（或从零分析），在**回复末尾只输出最终修正后的配置 JSON**：

```json
{
  "transport": "stdio",
  "command": "启动命令",
  "args": ["参数列表"],
  "cwd": "服务器目录的绝对路径",
  "name": "服务器名",
  "description": "描述",
  "env": {} 或 { "KEY": "value" }
}
```

- **最终只输出配置 JSON**，无需额外文字说明
- **禁止**使用任何方式直接修改 `mcp_servers.json` 或任何配置文件！
  写配置、补全字段、启动服务器全部由系统自动完成
- 配置输出后，由系统自动捕获并展示给用户预览确认，用户点「确认安装」后由系统完成写入与启动
- 参考 `references/config-templates.md` 中的各类型配置模板

## 配套机制

| 环节 | 处理方 | 说明 |
|------|--------|------|
| 环境变量弹窗 | 系统 | 自动扫描项目中的环境变量占位，自动弹出输入框 |
| 配置提交 | 系统 | 捕获 AI 回复末尾的 JSON → 前端预览 → 用户确认 → 自动写入配置并启动 |
| 项目分析 | AI | 浏览文件、阅读入口、安装依赖 |
| 配置审阅 | AI | 审阅系统草稿，在回复末尾输出修正后的配置 JSON |

## 配置注意事项

- 严格按照 README.md 中的配置示例，逐字段复制，不要自己发明配置
- 如果 README 推荐使用 `npx` → `"command": "npx"` + `"args": ["-y", "包名"]`
- 如果 README 推荐 `pip install` + `python -m` 运行 → `"command": "python"` + `"args": ["-m", "模块名"]`
- 如果使用 `uvx` 方式 → `"command": "uvx"` + `"args": ["包名"]`
- 如果使用本地 `node` 脚本 → `"command": "node"` + `"args": ["入口文件"]`
- cwd 设置为服务器文件所在目录（绝对路径）
- 文档提到需要环境变量（API Key 等）时，在 env 字段中**留空字符串**，后续由用户填写
- **绝不要**把示例值/占位值写入 env 字段。以下模式均为占位符而非真实密钥，识别到应忽略并在 env 中留空：`YOUR_XXX` / `YOURS_XXX`（如 `YOUR_PROMPT_COMPASS_API_KEY`）、尖括号 `<your_key>` / `<api_key>`、`changeme` / `change_me`、`placeholder`、连续 `xxx` / `XXXX` 串、空字符串 `""`。用户密钥必须由用户通过弹窗填写，AI 无权代填
- 不要指定 `enabled` / `auto_start` 字段，系统会自动处理
