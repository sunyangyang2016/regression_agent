"""
技能基类 - 所有技能必须继承此类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# 技能执行默认超时时间（秒）
# SkillExecutor 与 SkillDispatcher 统一使用，避免两处默认值不一致导致行为漂移
DEFAULT_SKILL_TIMEOUT = 60.0



@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseSkill(ABC):
    """技能基类 - 所有技能必须继承此类"""

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    category: str = "general"
    tags: list = []
    priority: int = 100
    input_schema: Dict[str, Any] = None
    """参数 JSON Schema（可选），用于 AI 识别技能所需的参数格式
    格式示例：
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "处理内容"}
        },
        "required": ["query"]
    }
    """

    triggers: list = []
    """声明式触发器配置（可选），加载后由 TriggerEngine 自动注册
    格式示例：
    [
        {"type": "keyword", "keywords": ["翻译", "translate"]},
        {"type": "pattern", "patterns": [r"把\\s*(.+?)\\s*翻译"]},
        {"type": "intent", "intents": ["translate"], "patterns": [...]},
    ]
    """

    def __init__(self):
        self._created_at = datetime.now()
        self._execution_count = 0

    @abstractmethod
    async def execute(self, context: "SkillContext", **kwargs) -> SkillResult:
        """执行技能逻辑（子类必须实现）"""
        ...

    # ---- 生命周期钩子（可选重写） ----

    def on_load(self):
        """技能被加载/注册时调用"""
        pass

    def on_unload(self):
        """技能被卸载/注销时调用"""
        pass

    def on_enable(self):
        """技能被启用时调用"""
        pass

    def on_disable(self):
        """技能被禁用时调用"""
        pass

    def set_enabled(self, enabled: bool):
        """运行时切换技能启用状态，并触发对应生命周期钩子"""
        was_enabled = bool(self.enabled)
        self.enabled = enabled
        if enabled and not was_enabled:
            self.on_enable()
        elif not enabled and was_enabled:
            self.on_disable()

    def get_metadata(self) -> Dict[str, Any]:
        """获取技能元数据"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "category": self.category,
            "tags": self.tags,
            "priority": self.priority,
            "input_schema": self.input_schema,
            "triggers": self.triggers,
            "execution_count": self._execution_count,
            "created_at": self._created_at.isoformat(),
        }

    def validate(self) -> bool:
        """验证技能配置是否有效"""
        return bool(self.name and self.description)
