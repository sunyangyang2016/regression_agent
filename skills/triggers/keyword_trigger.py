"""
关键词触发器 - 根据用户输入中的关键词触发技能
"""
import re
from typing import Callable, List, Optional


class KeywordTrigger:
    """关键词触发器 - 匹配用户输入中的特定关键词"""

    def __init__(self, keywords: List[str], skill_name: str, case_sensitive: bool = False):
        self.keywords = [k.lower() for k in keywords]
        self.skill_name = skill_name
        self.case_sensitive = case_sensitive

    def check(self, user_input: str) -> bool:
        """检查用户输入是否包含触发关键词"""
        text = user_input if self.case_sensitive else user_input.lower()
        return any(kw in text for kw in self.keywords)

    def get_match_info(self, user_input: str) -> Optional[dict]:
        """获取匹配信息"""
        text = user_input if self.case_sensitive else user_input.lower()
        for kw in self.keywords:
            if kw in text:
                return {
                    "trigger_type": "keyword",
                    "matched_keyword": kw,
                    "skill_name": self.skill_name,
                }
        return None