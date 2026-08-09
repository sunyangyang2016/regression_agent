"""
Agent Chat 省 Token 优化器

核心策略：
S1. 稳定 System Prompt（利用 Prompt Cache）
    将动态注入的工具清单、MCP 服务器状态与静态 system prompt 分离。
    第一条 system 消息保持稳定 -> 支持 prompt cache 的 API（DeepSeek/GLM/Claude/Kimi 等）
    可命中缓存前缀，成本大幅下降（缓存命中价格通常为 1/10 ~ 1/50）。

S4. 消息瘦身（安全无副作用）
    仅清理空 system 消息、重复 system 消息，不修改任何用户/助手/工具消息内容。

S6. 请求统计
    每次请求前估算优化前后 token 数，打印对比，便于观察省 token 效果。
"""
import re
from typing import Dict, List, Optional, Tuple


class AgentTokenOptimizer:
    """Agent Chat 省 Token 优化器"""

    # 动态内容 marker（对应 AIClient 中注入的标记）
    TOOL_LIST_MARKER = "## 当前已安装的工具清单"
    MCP_STATUS_MARKER = "## MCP 服务器状态"
    MCP_TOOLS_MARKER = "## 可用工具"
    _DYNAMIC_MARKERS = (TOOL_LIST_MARKER, MCP_STATUS_MARKER, MCP_TOOLS_MARKER)

    def __init__(self, enabled: bool = True, verbose: bool = True):
        self.enabled = enabled
        self.verbose = verbose
        self._last_stats: Dict = {}

    # ===================================================
    # 对外主接口
    # ===================================================

    def optimize_messages(self, messages: List[dict]) -> Tuple[List[dict], Dict]:
        """对消息列表做全套优化（幂等，可重复调用）

        Args:
            messages: OpenAI 格式消息列表（不会被原地修改）

        Returns:
            (optimized_messages, stats)

        说明：
        - S1 分离动作本身不减少文本量（动态内容本来就必须发送），
          核心价值是保持第一条 system 稳定以命中 prompt cache 降价。
        - 真正的 token 减少来自 S4 瘦身（删除空消息、重复 system）。
        """
        if not self.enabled or not messages:
            return messages, {"triggered": False, "reason": "disabled or empty"}

        before_tokens = self._count_tokens(messages)
        result = list(messages)

        # S1: 稳定 system prompt —— 动态内容移入末尾独立 system 消息
        result = self._stabilize_system_prompt(result)

        # S4: 消息瘦身 —— 清理冗余 system 消息
        result = self._slim_messages(result)

        after_tokens = self._count_tokens(result)
        # 判断真正的内容减少（排除消息 overhead 影响：用纯文本 token 对比）
        base_text = " ".join(str(m.get("content", "") or "") for m in messages)
        result_text = " ".join(str(m.get("content", "") or "") for m in result)
        base_text_tokens = self._count_text_tokens(base_text)
        result_text_tokens = self._count_text_tokens(result_text)
        content_saved = base_text_tokens - result_text_tokens

        stats = {
            "triggered": content_saved > 0 or base_text != result_text,
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "text_before_tokens": base_text_tokens,
            "text_after_tokens": result_text_tokens,
            "saved_tokens": max(0, content_saved),
            "saved_ratio": round(max(0, content_saved) / max(base_text_tokens, 1) * 100, 1),
            "dynamic_separated": self._has_dynamic_appended(result),
            "system_stable": not any(
                any(marker in str(msg.get("content", "") or "") for marker in self._DYNAMIC_MARKERS)
                for msg in (result[0:1] if result else [])
            ),
        }
        self._last_stats = stats

        if self.verbose and (content_saved > 0 or stats.get("dynamic_separated")):
            msg = f"[TokenOptimizer] 📊 优化完成: "
            if content_saved > 0:
                msg += f"内容节省 {content_saved} tokens"
            if stats.get("dynamic_separated"):
                msg += " | ✅ system prompt 已稳定（可命中 Prompt Cache）"
            print(msg)

        return result, stats

    # ===================================================
    # S1: 稳定 System Prompt
    # ===================================================

    def _stabilize_system_prompt(self, messages: List[dict]) -> List[dict]:
        """将动态内容从 system 消息中拆离到末尾独立 system 消息

        目标结构：
        [system(静态，稳定)] + [对话消息...] + [system(动态)]

        幂等：重复调用时，已分离的静态 system 不受影响，
        末尾的纯动态 system 会被重新提取并合并到末尾。
        """
        if not messages:
            return messages

        dynamic_blocks: List[str] = []
        result: List[dict] = []

        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", "") or "")

            if role == "system":
                extracted = self._extract_dynamic_blocks(content)
                if extracted:
                    dynamic_blocks.extend(extracted)
                    # 计算静态部分（移除动态块后的剩余内容）
                    static = self._remove_dynamic_blocks(content)
                    if static.strip():
                        result.append({"role": "system", "content": static.strip()})
                    # 如果 static 为空（纯动态消息），跳过（会重新合并到末尾）
                    continue

            result.append(msg)

        # 确保第一条消息是 system（稳定 prompt 基准）
        if not result or result[0].get("role") != "system":
            result.insert(0, {"role": "system", "content": "你是一个有帮助的AI助手。"})

        # 追加合并后的动态 system 消息到末尾
        if dynamic_blocks:
            combined_dynamic = "\n\n".join(
                block.strip() for block in dynamic_blocks if block.strip()
            )
            if combined_dynamic:
                result.append({"role": "system", "content": combined_dynamic})

        return result

    def _extract_dynamic_blocks(self, content: str) -> List[str]:
        """从 system 内容中提取动态块（可用工具 + 工具清单 + MCP 状态）"""
        blocks: List[str] = []

        # 按出现顺序扫描所有动态 marker，提取对应块直到下一 marker 或文本末尾
        positions = []
        for marker in self._DYNAMIC_MARKERS:
            if marker in content:
                positions.append((content.index(marker), marker))
        # 按起始位置排序
        positions.sort(key=lambda x: x[0])

        # 提取每个 marker 块（到下一 marker 之前）
        for i, (pos, marker) in enumerate(positions):
            end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(content)
            block = content[pos:end_pos].strip()
            if block:
                blocks.append(block)

        return blocks

    def _remove_dynamic_blocks(self, content: str) -> str:
        """从内容中移除动态块，返回静态部分（不改变原内容之外的任何信息）"""
        if not content:
            return content

        result = content
        for marker in self._DYNAMIC_MARKERS:
            if marker in result:
                idx = result.find(marker)
                # 从当前 marker 到文本末尾（或下一个 marker 之前）
                end_idx = len(result)
                rest = result[idx + len(marker):]
                for next_marker in self._DYNAMIC_MARKERS:
                    if next_marker != marker and next_marker in rest:
                        end_idx = idx + len(marker) + rest.find(next_marker)
                        break
                result = result[:idx] + result[end_idx:]

        # 清理多余空行
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    # ===================================================
    # S4: 消息瘦身
    # ===================================================

    def _slim_messages(self, messages: List[dict]) -> List[dict]:
        """清理冗余消息（安全：不修改任何消息内容，仅删除明显冗余的）

        处理项：
        - 空内容的 system 消息
        - 空内容的 assistant 消息（无 content 且无 tool_calls）
        - 完全重复的连续 system 消息
        - 多个动态 system 消息仅保留最后一个
        """
        if not messages:
            return messages

        result: List[dict] = []
        seen_dynamic = False
        prev_role: Optional[str] = None

        for msg in messages:
            role = msg.get("role", "")
            raw_content = msg.get("content", "")
            content = str(raw_content) if raw_content is not None else ""

            # 删除空 system 消息（纯空内容，无任何信息价值）
            if role == "system" and not content.strip():
                continue

            # 删除空的 assistant 消息（无 content 且无 tool_calls）
            if role == "assistant" and not content.strip() and "tool_calls" not in msg:
                continue

            # 动态 system 消息只保留最后一个（防止重复注入）
            if role == "system" and any(m in content for m in self._DYNAMIC_MARKERS):
                if seen_dynamic:
                    continue  # 已有更早的动态 system，跳过
                seen_dynamic = True

            # 完全重复的连续 system 消息去重
            if role == "system" and prev_role == "system":
                prev_content = str(result[-1].get("content", "")) if result else ""
                if prev_content == content:
                    continue

            result.append(msg)
            prev_role = role

        return result

    # ===================================================
    # 辅助方法
    # ===================================================

    @staticmethod
    def _count_tokens(messages: List[dict]) -> int:
        """估算 token 数（复用项目现有 TokenCounter，失败时回退到简易估算）"""
        try:
            from ai.token_counter import TokenCounter
            return TokenCounter.count_messages(messages)
        except ImportError:
            total = 0
            for msg in messages:
                text = str(msg.get("content", "") or "")
                chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
                other_chars = len(text) - chinese_chars
                total += chinese_chars * 2 + other_chars
            return int(total)

    @staticmethod
    def _count_text_tokens(text: str) -> int:
        """估算纯文本的 token 数（不含消息 overhead）"""
        if not text:
            return 0
        try:
            from ai.token_counter import TokenCounter
            return TokenCounter.count_text(text)
        except ImportError:
            chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            other_chars = len(text) - chinese_chars
            return int(chinese_chars * 2 + other_chars)

    @staticmethod
    def _has_dynamic_appended(messages: List[dict]) -> bool:
        """检查消息列表末尾是否已追加动态 system 消息"""
        if not messages:
            return False
        last = messages[-1]
        content = str(last.get("content", "") or "")
        return last.get("role") == "system" and any(
            marker in content for marker in AgentTokenOptimizer._DYNAMIC_MARKERS
        )

    @property
    def last_stats(self) -> Dict:
        """最近一次优化的统计信息"""
        return self._last_stats
