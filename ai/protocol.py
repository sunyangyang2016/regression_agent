"""
AI 消息协议定义
标准化的消息格式、回调接口、事件类型
"""
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCallInfo:
    """工具调用信息"""
    id: str
    name: str
    arguments: dict
    result: Optional[str] = None
    status: str = "pending"  # pending | running | success | error


@dataclass
class Message:
    """标准消息体"""
    role: MessageRole
    content: str
    tool_calls: list = field(default_factory=list)  # ToolCallInfo 列表
    tool_call_id: Optional[str] = None


@dataclass
class AIStreamEvent:
    """流式事件"""
    type: str  # chunk | tool_call | tool_result | round | complete | error | cancelled
    data: Any = None
    error: Optional[str] = None


class AIStreamCallback:
    """流式回调（异步友好）"""
    
    def __init__(self):
        self.on_chunk: Optional[Callable[[str], None]] = None
        self.on_tool_call: Optional[Callable[[ToolCallInfo], None]] = None
        self.on_tool_result: Optional[Callable[[ToolCallInfo], None]] = None
        self.on_complete: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None


class ModelConfig:
    """模型配置"""
    def __init__(self, base_url: str = "", api_key: str = "", model: str = "",
                 temperature: float = 0.7, max_tokens: int = 4096, stream: bool = True,
                 max_context: int = 65536):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.max_context = max_context
    
    @classmethod
    def from_dict(cls, config: dict) -> "ModelConfig":
        return cls(
            base_url=config.get("api", {}).get("base_url", ""),
            api_key=config.get("api", {}).get("api_key", ""),
            model=config.get("api", {}).get("model", ""),
            temperature=config.get("chat", {}).get("temperature", 0.7),
            max_tokens=config.get("chat", {}).get("max_tokens", 4096),
            stream=config.get("chat", {}).get("stream", True),
            max_context=config.get("api", {}).get("max_context", 65536),
        )
