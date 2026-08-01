# Agent - API 文档

## 概览

Agent 提供 RESTful HTTP API 和 WebSocket 实时通信接口，支持外部系统集成和远程控制。

- **Base URL**: `http://localhost:8000`
- **认证**: Bearer Token（可选，通过 `API_KEY` 配置）
- **格式**: 请求/响应均为 JSON

---

## 认证

若配置了 `API_KEY`，所有请求需在 Header 中携带：

```
Authorization: Bearer <your_api_key>
```

---

## REST API

### 健康检查

```
GET /health
```

**响应示例:**
```json
{
    "status": "ok",
    "version": "1.0.0",
    "uptime": 3600
}
```

---

### 发送消息

```
POST /api/chat
```

**请求体:**
```json
{
    "message": "你好，请介绍一下你自己",
    "model": "deepseek-chat",
    "stream": false
}
```

**参数说明:**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户消息内容 |
| model | string | 否 | 模型名称，默认使用当前模型 |
| stream | boolean | 否 | 是否使用流式输出，默认 false |

**响应示例:**
```json
{
    "id": "conv_123",
    "reply": "你好！我是 Agent，一个 AI 智能助手...",
    "model": "deepseek-chat",
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 128,
        "total_tokens": 153
    }
}
```

---

### 获取会话列表

```
GET /api/conversations
```

**查询参数:**
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 返回数量，默认 50 |
| offset | int | 偏移量，默认 0 |

---

### 获取会话详情

```
GET /api/conversations/{id}
```

---

### 删除会话

```
DELETE /api/conversations/{id}
```

---

### 获取模型列表

```
GET /api/models
```

**响应示例:**
```json
{
    "models": [
        {
            "id": "deepseek-chat",
            "provider": "deepseek",
            "name": "DeepSeek Chat",
            "status": "online"
        }
    ]
}
```

---

### 获取工具列表

```
GET /api/tools
```

**响应示例:**
```json
{
    "tools": [
        {
            "id": "web_scraper",
            "name": "网页抓取",
            "description": "抓取指定 URL 的内容",
            "enabled": true
        }
    ]
}
```

---

### 获取插件列表

```
GET /api/plugins
```

---

### 启用/禁用插件

```
POST /api/plugins/{id}/toggle
```

**请求体:**
```json
{
    "enabled": true
}
```

---

### 系统配置

```
GET /api/config
```

返回当前系统配置（不包含敏感信息）。

---

## WebSocket API

### 连接

```
ws://localhost:8000/ws
```

如需认证，在连接 URL 后附加 token 参数：
```
ws://localhost:8000/ws?token=<your_api_key>
```

### 消息格式

**发送消息:**
```json
{
    "type": "message",
    "data": {
        "content": "你好",
        "model": "deepseek-chat"
    }
}
```

**接收消息（流式）:**
```json
{
    "type": "stream",
    "data": {
        "content": "正在",
        "done": false
    }
}
```

**接收消息（完成）:**
```json
{
    "type": "message_done",
    "data": {
        "id": "conv_123",
        "content": "你好！我是 Agent...",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 50,
            "total_tokens": 60
        }
    }
}
```

### 事件推送

服务器会主动推送以下事件：

| 事件类型 | 说明 |
|----------|------|
| plugin_changed | 插件状态变更 |
| tool_registered | 新工具注册 |
| skill_loaded | 技能加载完成 |
| system_notification | 系统通知 |

---

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证/无效 Token |
| 404 | 资源不存在 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |

**错误响应格式:**
```json
{
    "error": {
        "code": 400,
        "message": "缺少必要参数: message",
        "details": null
    }
}