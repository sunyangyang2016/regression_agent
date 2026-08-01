"""
Prompt 构建器 - 构建发送给 AI 的消息
"""
from typing import Any, Dict, List, Optional
from ai.token_counter import TokenCounter


class PromptBuilder:
    """Prompt 构建器"""

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt
        self._token_counter = TokenCounter()

    def build_messages(
        self,
        user_input: str,
        history: Optional[List[Dict]] = None,
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4096,
    ) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = []

        # System prompt
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 添加上下文
        if context:
            context_str = self._build_context(context)
            if context_str:
                messages.append({"role": "system", "content": context_str})

        # 添加历史消息
        if history:
            # 截断历史以控制 Token 数
            remaining = max_tokens - self._token_counter.count_text(user_input)
            messages.extend(self._truncate_history(history, remaining))

        # 添加当前用户输入
        messages.append({"role": "user", "content": user_input})

        return messages

    def build_with_skills(
        self,
        user_input: str,
        skill_prompt: str = "",
        history: Optional[List[Dict]] = None,
    ) -> List[Dict[str, str]]:
        """构建带有技能上下文的 Prompt"""
        system = self.system_prompt
        if skill_prompt:
            system += skill_prompt
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-20:])  # 仅保留最近 20 条
        messages.append({"role": "user", "content": user_input})
        return messages

    def _build_context(self, context: Dict[str, Any]) -> str:
        """构建上下文文本"""
        parts = []
        for key, value in context.items():
            if isinstance(value, str):
                parts.append(f"{key}: {value}")
            elif isinstance(value, (list, dict)):
                import json
                parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        return "\n".join(parts)

    def _truncate_history(self, history: List[Dict], max_tokens: int) -> List[Dict]:
        """截断历史消息以适应 Token 限制"""
        result = []
        total = 0
        for msg in reversed(history):
            tokens = self._token_counter.count_text(msg.get("content", ""))
            if total + tokens > max_tokens:
                break
            total += tokens
            result.insert(0, msg)
        return result