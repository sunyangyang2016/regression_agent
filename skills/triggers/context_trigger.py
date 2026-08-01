"""
上下文触发器 - 基于对话上下文状态触发技能
"""
from typing import Any, Dict, Optional, Callable


class ContextTrigger:
    """上下文触发器 - 根据对话历史或状态触发"""

    def __init__(self, skill_name: str, condition: Callable[[Dict[str, Any]], bool]):
        self.skill_name = skill_name
        self.condition = condition

    def check(self, context: Dict[str, Any]) -> bool:
        """检查上下文是否满足触发条件"""
        try:
            return self.condition(context)
        except Exception:
            return False

    def get_match_info(self, context: Dict[str, Any]) -> Optional[dict]:
        """获取匹配信息"""
        if self.check(context):
            return {
                "trigger_type": "context",
                "skill_name": self.skill_name,
                "context_keys": list(context.keys()),
            }
        return None