"""
正则模式触发器 - 基于正则表达式模式匹配触发技能
"""
import re
from typing import Optional, Pattern


class PatternTrigger:
    """正则模式触发器 - 使用正则表达式匹配用户输入"""

    def __init__(self, pattern: str, skill_name: str, flags: int = re.IGNORECASE):
        self.pattern_str = pattern
        self.pattern: Pattern = re.compile(pattern, flags)
        self.skill_name = skill_name

    def check(self, user_input: str) -> bool:
        """检查用户输入是否匹配正则模式"""
        return bool(self.pattern.search(user_input))

    def get_match_info(self, user_input: str) -> Optional[dict]:
        """获取匹配信息"""
        match = self.pattern.search(user_input)
        if match:
            return {
                "trigger_type": "pattern",
                "pattern": self.pattern_str,
                "matched_text": match.group(),
                "skill_name": self.skill_name,
            }
        return None