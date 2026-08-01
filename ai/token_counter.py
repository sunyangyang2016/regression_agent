"""
Token 计数工具
"""
import re
from typing import Optional


class TokenCounter:
    """Token 计数器"""

    @staticmethod
    def count_text(text: str) -> int:
        """估算文本的 Token 数量"""
        if not text:
            return 0
        # 简单估算：中文约 1.5 tokens/字，英文约 0.25 tokens/字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z0-9]', text))
        other_chars = len(text) - chinese_chars - english_chars
        return int(chinese_chars * 1.5 + english_chars * 0.25 + other_chars * 0.5) + 1

    @staticmethod
    def count_messages(messages: list) -> int:
        """计算消息列表的总 Token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += TokenCounter.count_text(content)
            # 每条消息附加 overhead
            total += 4
        return total

    @staticmethod
    def truncate_to_limit(text: str, max_tokens: int) -> str:
        """截断文本到指定 Token 数"""
        tokens = TokenCounter.count_text(text)
        if tokens <= max_tokens:
            return text
        ratio = max_tokens / tokens
        cut_len = int(len(text) * ratio)
        return text[:cut_len] + "\n... [截断]"

    @staticmethod
    def format_tokens(count: int) -> str:
        """格式化 Token 数显示"""
        if count < 1000:
            return f"{count}"
        return f"{count/1000:.1f}K"