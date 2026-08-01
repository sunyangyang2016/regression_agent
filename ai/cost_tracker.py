"""
成本追踪器 - 追踪 AI API 调用成本
"""
from typing import Dict, Optional
from datetime import datetime, date


# 模型定价（每 1K tokens 的 USD 价格）
MODEL_PRICING = {
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
    "deepseek-chat": {"input": 0.0005, "output": 0.002},
    "deepseek-coder": {"input": 0.001, "output": 0.002},
    "claude-3": {"input": 0.015, "output": 0.075},
    "gemini-pro": {"input": 0.001, "output": 0.002},
}


class CostTracker:
    """AI 调用成本追踪器"""

    def __init__(self):
        self._sessions: Dict[str, list] = {}

    def record(self, model: str, input_tokens: int, output_tokens: int, session_id: Optional[str] = None):
        """记录一次 API 调用的成本"""
        pricing = MODEL_PRICING.get(model, {"input": 0.001, "output": 0.002})
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost

        record = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
        }

        key = session_id or date.today().isoformat()
        if key not in self._sessions:
            self._sessions[key] = []
        self._sessions[key].append(record)
        return record

    def get_session_cost(self, session_id: str) -> float:
        """获取指定会话的总成本"""
        records = self._sessions.get(session_id, [])
        return sum(r["total_cost"] for r in records)

    def get_daily_cost(self, target_date: Optional[str] = None) -> float:
        """获取指定日期的总成本"""
        if target_date is None:
            target_date = date.today().isoformat()
        return self.get_session_cost(target_date)

    def get_total_cost(self) -> float:
        """获取所有会话的总成本"""
        total = 0.0
        for records in self._sessions.values():
            total += sum(r["total_cost"] for r in records)
        return total

    def get_stats(self) -> Dict:
        """获取汇总统计"""
        total_input = 0
        total_output = 0
        total_cost = 0.0
        for records in self._sessions.values():
            for r in records:
                total_input += r["input_tokens"]
                total_output += r["output_tokens"]
                total_cost += r["total_cost"]
        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost": round(total_cost, 4),
            "session_count": len(self._sessions),
            "model_pricing": MODEL_PRICING,
        }

    def reset(self):
        """重置所有记录"""
        self._sessions.clear()