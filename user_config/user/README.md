# 用户配置目录

此目录存放用户的个性化配置，**默认只有一个 README 文档**。

## 工作机制

- 系统读取配置时，**优先**查找本目录（`user_config/user/`）下的配置文件；
- 若本目录下不存在对应文件，则自动回退使用 `user_config/defaults/` 目录下的默认配置；
- 当您首次保存某类配置（例如模型列表、MCP 服务器、内置工具开关等）时，系统会自动在本目录下创建对应的 JSON 文件；
- `user_config/defaults/` 目录下的默认配置**永远不会被修改**。

## 示例

例如，当您首次配置/保存 MCP 服务器时，系统会自动创建：

```
user_config/user/mcp_servers.json
```

之后读取 MCP 服务器配置时，将优先使用此文件；若未创建，则使用默认配置。

## 配置文件与默认配置对应关系

| 用户配置文件 | 默认配置文件 | 说明 |
| --- | --- | --- |
| `models.json` | `defaults/models.json` | 模型列表 |
| `mcp_servers.json` | `defaults/mcp_servers.json` | MCP 服务器配置 |
| `builtin_tools_config.json` | `defaults/builtin_tools_config.json` | 内置工具开关 |
| `ui_state.json` | `defaults/ui_state.json` | UI 界面状态（面板/侧边栏/插件 Tab） |
| 其他 JSON | `defaults/` 下对应文件 | 其他配置 |
</