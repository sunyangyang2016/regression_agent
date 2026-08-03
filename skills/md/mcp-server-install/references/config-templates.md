# MCP 服务器配置模板参考

以下为各类常见 MCP 服务器启动方式的配置模板，供 `mcp_finalize_install` 构造配置 JSON 时参考。

## npx 方式

适用于 Node.js 生态、通过 npm 包发布的 MCP 服务器。

```json
{
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@scope/mcp-server-package"],
  "cwd": "E:\\path\\to\\server",
  "name": "服务器名称",
  "description": "描述",
  "env": {}
}
```

## pip + python 方式

适用于 Python 生态、通过 `pip install` 安装后使用 `python -m` 运行的 MCP 服务器。

```json
{
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "mcp_server"],
  "cwd": "E:\\path\\to\\server",
  "name": "服务器名称",
  "description": "描述",
  "env": {}
}
```

## uvx 方式

适用于 Python 生态、通过 `uvx` 直接运行的 MCP 服务器包。

```json
{
  "transport": "stdio",
  "command": "uvx",
  "args": ["mcp-server-package"],
  "cwd": "E:\\path\\to\\server",
  "name": "服务器名称",
  "description": "描述",
  "env": {}
}
```

## node 本地脚本

适用于直接克隆到本地、有 Node.js 入口脚本的 MCP 服务器项目。

```json
{
  "transport": "stdio",
  "command": "node",
  "args": ["dist/server.js"],
  "cwd": "E:\\path\\to\\server",
  "name": "服务器名称",
  "description": "描述",
  "env": {}
}
```

## HTTP 远程

适用于流式 HTTP（Streamable HTTP）远程托管的 MCP 服务，无需本地启动子进程。

```json
{
  "transport": "http",
  "url": "https://example.com/mcp",
  "name": "服务器名称",
  "description": "描述",
  "env": {}
}
```

## 带环境变量的配置

当服务器需要 API Key / Token 等环境变量时（如第 4 步 `mcp_env_setup` 弹窗），在 env 字段中留空字符串，后续由用户填写：

```json
{
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "mcp_server"],
  "cwd": "E:\\path\\to\\server",
  "name": "服务器名称",
  "description": "描述",
  "env": {
    "ANTHROPIC_API_KEY": ""
  }
}
```

## 注意事项

- **cwd 使用绝对路径**，通常是服务器文件下载到的目录（`tools/mcp/server/{仓库名}`）
- **严禁自创字段**，严格按照 README.md 中的配置示例
- **不要包含** `enabled` / `auto_start` 字段，后端会自动处理
- 最终只输出配置 JSON，无需额外说明