"""
事件触发器 - 基于系统事件触发技能
"""
from typing import Any, Dict, List, Optional


class EventTrigger:
    """事件触发器 - 当特定系统事件发生时触发技能"""

    def __init__(self, skill_name: str, event_names: List[str]):
        self.skill_name = skill_name
        self.event_names = event_names

    def check(self, event_name: str, event_data: Optional[Dict[str, Any]] = None) -> bool:
        """检查事件是否匹配"""
        return event_name in self.event_names

    def get_match_info(
        self, event_name: str, event_data: Optional[Dict[str, Any]] = None
    ) -> Optional[dict]:
        """获取匹配信息"""
        if self.check(event_name, event_data):
            return {
                "trigger_type": "event",
                "event_name": event_name,
                "skill_name": self.skill_name,
                "event_data": event_data,
            }
        return None