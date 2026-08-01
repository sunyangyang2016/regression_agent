"""
意图触发器 - 基于用户输入意图的分类触发
"""
from typing import List, Optional


class IntentTrigger:
    """意图触发器 - 通过关键词模式识别用户意图"""

    def __init__(self, intent_name: str, skill_name: str, patterns: List[str]):
        self.intent_name = intent_name
        self.skill_name = skill_name
        self.patterns = [p.lower() for p in patterns]

    def check(self, user_input: str) -> bool:
        """检查用户输入是否匹配此意图"""
        text = user_input.lower()
        return any(p in text for p in self.patterns)

    def get_match_info(self, user_input: str) -> Optional[dict]:
        """获取匹配信息"""
        if self.check(user_input):
            return {
                "trigger_type": "intent",
                "intent_name": self.intent_name,
                "skill_name": self.skill_name,
            }
        return None