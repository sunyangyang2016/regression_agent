"""
技能上下文 - 技能执行时的上下文信息
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass
class SkillContext:
    """技能执行上下文"""

    user_input: str = ""
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    """技能参数（由 SkillDispatcher 从 arguments 注入）"""
    ai_client: Optional[Any] = None
    tool_manager: Optional[Any] = None
    event_bus: Optional[Any] = None
    config: Dict[str, Any] = field(default_factory=dict)
    skill_dispatcher: Optional[Any] = None
    """SkillDispatcher 引用（允许 skill 内部调用其他 skill）"""
    created_at: datetime = field(default_factory=datetime.now)

    def set(self, key: str, value: Any):
        """设置上下文变量"""
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文变量"""
        return self.variables.get(key, default)

    def set_metadata(self, key: str, value: Any):
        """设置元数据"""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "user_input": self.user_input,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "variables": self.variables,
            "params": self.params,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
        }
