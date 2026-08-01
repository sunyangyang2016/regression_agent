"""
API 数据模型
"""
from typing import Any, Dict, Optional
from datetime import datetime

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        """回退：无 pydantic 时的简单基类"""
        pass

    def Field(*args, **kwargs):
        return None


class ChatRequest(BaseModel):
    """聊天请求"""
    def __init__(self, **kwargs):
        self.message = kwargs.get("message", "")
        self.conversation_id = kwargs.get("conversation_id")
        self.stream = kwargs.get("stream", False)


class ChatResponse(BaseModel):
    """聊天响应"""
    def __init__(self, **kwargs):
        self.response = kwargs.get("response", "")
        self.conversation_id = kwargs.get("conversation_id", "")
        self.tokens_used = kwargs.get("tokens_used", 0)
        self.model = kwargs.get("model", "")


class ToolCallRequest(BaseModel):
    """工具调用请求"""
    def __init__(self, **kwargs):
        self.tool_name = kwargs.get("tool_name", "")
        self.arguments = kwargs.get("arguments", {})


class ToolCallResponse(BaseModel):
    """工具调用响应"""
    def __init__(self, **kwargs):
        self.success = kwargs.get("success", False)
        self.result = kwargs.get("result")
        self.error = kwargs.get("error")


class HealthResponse(BaseModel):
    """健康检查响应"""
    def __init__(self, **kwargs):
        self.status = kwargs.get("status", "ok")
        self.version = kwargs.get("version", "0.1.0")
        self.uptime = kwargs.get("uptime", 0.0)