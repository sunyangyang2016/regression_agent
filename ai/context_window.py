"""
上下文滑动窗口 + 压缩管理（独立模块）

功能：
1. 滑动窗口（自动触发）：超过 context 最大容量 90% 时，保留最新 50% 对话
2. 压缩（手动触发）：将旧对话压缩为摘要消息
"""
from typing import Callable, List, Optional
from ai.token_counter import TokenCounter


class ContextWindowManager:
    """上下文滑动窗口管理器

    Args:
        max_context: 模型上下文最大容量（token 数），默认 65536
        warning_ratio: 触发滑动的容量阈值比例，默认 0.9（90%）
        keep_ratio: 滑动后保留的数据比例，默认 0.5（保留最新 50%）
        summary_generator: 可选的 LLM 摘要生成回调 (removed_messages: list) -> str，
            为 None 时压缩使用本地截断（truncate）策略
    """

    def __init__(self,
                 max_context: int = 65536,
                 warning_ratio: float = 0.9,
                 keep_ratio: float = 0.5,
                 summary_generator: Optional[Callable[[list], str]] = None):
        self.max_context = max_context
        self.warning_ratio = warning_ratio
        self.keep_ratio = keep_ratio
        self.summary_generator = summary_generator

    # ==========================================
    # 对外主接口
    # ==========================================

    def should_slide(self, messages: list) -> bool:
        """判断当前消息列表是否达到触发阈值（超过 max_context × warning_ratio）"""
        total = self._count_tokens(messages)
        threshold = int(self.max_context * self.warning_ratio)
        return total > threshold

    def _count_tokens(self, messages: list) -> int:
        """计算消息列表的总 token 数"""
        if not messages:
            return 0
        return TokenCounter.count_messages(messages)

    def check_and_slide(self, messages: List[dict]) -> tuple:
        """检查并执行自动滑动（超过 90% 容量时触发）"""
        before_tokens = self._count_tokens(messages)
        if not self.should_slide(messages):
            return messages, {"triggered": False}
        prompt_msgs, units = self._split_units(messages)
        if not units:
            return messages, {"triggered": False}
        kept_units = self._keep_latest_units(units, before_tokens)
        new_messages = self._rebuild(prompt_msgs, kept_units)
        stats = {
            "triggered": True,
            "before_tokens": before_tokens,
            "after_tokens": self._count_tokens(new_messages),
            "removed_units": len(units) - len(kept_units),
            "prompt_tokens": self._count_tokens(prompt_msgs),
            "kept_units": len(kept_units),
        }
        return new_messages, stats

    def force_slide(self, messages, target_ratio=None):
        """强制滑动：不依赖 token 估算阈值，直接保留最新 keep_ratio 比例对话单元

        调用方已用真实累计 token 判断超限时使用（TokenCounter 估算与真实值偏差大，
        导致界面已超限但 check_and_slide 内部估算未触发）。system prompt 始终保留最前。
        """
        ratio = target_ratio if target_ratio is not None else self.keep_ratio
        prompt_msgs, units = self._split_units(messages)
        if len(units) <= 1:
            return messages, {
                "triggered": False,
                "before_units": len(units),
                "removed_units": 0,
                "kept_units": len(units),
                "reason": "对话单元过少，无需滑动",
            }
        keep_count = max(1, int(len(units) * ratio))
        kept_units = units[-keep_count:]
        new_messages = self._rebuild(prompt_msgs, kept_units)
        return new_messages, {
            "triggered": True,
            "before_units": len(units),
            "removed_units": len(units) - len(kept_units),
            "kept_units": len(kept_units),
            "keep_ratio": ratio,
        }

    def compress(self, messages: List[dict], strategy: str = "truncate") -> tuple:
        """手动压缩上下文（由用户主动触发）。

        将较旧的对话单元压缩为一条摘要消息放入 context，
        保留最新 keep_ratio 比例的原始对话单元。

        Args:
            messages: 当前消息列表（不会被原地修改）
            strategy: "truncate"（本地截断）或 "summarize"（LLM 回调）

        Returns:
            (new_messages, stats)
        """
        before_tokens = self._count_tokens(messages)
        prompt_msgs, units = self._split_units(messages)

        if len(units) <= 1:
            return messages, {
                "triggered": False,
                "before_tokens": before_tokens,
                "after_tokens": before_tokens,
                "compressed_units": 0,
                "kept_units": len(units),
                "strategy": strategy,
                "reason": "对话内容过短，无需压缩",
            }

        keep_count = max(1, int(len(units) * self.keep_ratio))
        kept_units = units[-keep_count:]
        removed_units = units[:-keep_count]

        summary_msg = self._build_summary_message(removed_units, strategy)
        new_messages = self._rebuild(prompt_msgs, kept_units, extra_before=summary_msg)

        stats = {
            "triggered": True,
            "before_tokens": before_tokens,
            "after_tokens": self._count_tokens(new_messages),
            "compressed_units": len(removed_units),
            "kept_units": len(kept_units),
            "strategy": strategy,
        }
        return new_messages, stats

    # ==========================================
    # 内部工具方法
    # ==========================================

    def _split_units(self, messages):
        """将消息拆分为 (system prompt 列表, 对话单元列表)"""
        prompt_msgs = []
        units = []
        current_unit = []

        for msg in messages:
            role = msg.get("role", "")
            if role == "system":
                prompt_msgs.append(msg)
                continue
            if role == "user":
                if current_unit:
                    units.append(current_unit)
                current_unit = [msg]
            else:
                if current_unit:
                    current_unit.append(msg)
                else:
                    units.append([msg])

        if current_unit:
            units.append(current_unit)

        return prompt_msgs, units

    def _unit_tokens(self, unit):
        """计算单个对话单元的 token 数"""
        return self._count_tokens(unit)

    def _keep_latest_units(self, units, total_tokens):
        """从最新单元开始往前保留，直到达到目标 token 比例（keep_ratio）

        至少保留最新 1 个单元（保证用户最新消息不会被丢弃）。
        """
        target = int(total_tokens * self.keep_ratio)
        kept = []
        kept_tokens = 0

        for unit in reversed(units):
            unit_tok = self._unit_tokens(unit)
            if kept and kept_tokens + unit_tok > target:
                break
            kept.insert(0, unit)
            kept_tokens += unit_tok

        return kept

    def _rebuild(self, prompt_msgs, kept_units, extra_before=None):
        """重组消息列表：[system...] + [extra_before] + [保留的对话单元...]"""
        new_messages = list(prompt_msgs)
        if extra_before is not None:
            new_messages.append(extra_before)
        for unit in kept_units:
            new_messages.extend(unit)
        return new_messages

    def _build_summary_message(self, removed_units, strategy):
        """将需要压缩的旧对话单元生成一条摘要消息"""
        removed_messages = []
        for unit in removed_units:
            removed_messages.extend(unit)

        if strategy == "summarize" and self.summary_generator is not None:
            try:
                summary_text = self.summary_generator(removed_messages)
            except Exception as e:
                print(f"[ContextWindow] LLM 摘要失败，回退 truncate: {e}")
                summary_text = self._truncate_text(removed_messages)
        else:
            summary_text = self._truncate_text(removed_messages)

        if not summary_text.strip():
            summary_text = "（历史对话内容为空）"

        return {
            "role": "user",
            "content": "【历史对话摘要】（以下内容为压缩后的历史对话，供参考回顾）\n" + summary_text,
        }

    def _truncate_text(self, removed_messages):
        """本地截断式压缩：合并文本 + 按 token 上限截断"""
        lines = []
        for msg in removed_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content:
                continue
            content = str(content).replace("\n", " ").strip()
            if len(content) > 200:
                content = content[:200] + "..."
            if role == "assistant":
                lines.append("AI: " + content)
            elif role == "tool":
                lines.append("工具结果: " + content)
            else:
                lines.append("用户: " + content)

        merged = "\n".join(lines)
        max_tokens = max(1, int(self._count_tokens(removed_messages) / 2))
        if self._count_tokens([{"role": "user", "content": merged}]) <= max_tokens:
            return merged
        return TokenCounter.truncate_to_limit(merged, max_tokens)
