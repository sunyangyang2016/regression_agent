"""
成本追踪器 - 追踪 AI API 调用成本

计费单价来源：
- 优先从模型配置（ModelConfig.api）读取当前激活模型的三个单价（USD / 每百万 token）：
  price_per_million_hit_tokens / price_per_million_miss_tokens / price_per_million_output_tokens
- 配置文件缺失时回退到内置默认价（DEFAULT_PRICING），保证历史行为兼容

费用公式（每百万 token 计费）：
    费用 = 命中token / 1_000_000 × 命中单价
         + 未命中token / 1_000_000 × 未命中单价
         + 输出token / 1_000_000 × 输出单价
"""
from typing import Dict, Optional
from datetime import datetime, date


# 内置默认价（USD / 每百万 token），仅在模型配置未提供单价时兜底
DEFAULT_PRICING = {
    "hit": 0.07,
    "miss": 1.0,
    "output": 2.0,
}


def get_model_pricing(model_config=None, model_name: Optional[str] = None) -> dict:
    """从模型配置读取计费单价（USD / 每百万 token）

    Args:
        model_config: ModelConfig 实例（含 config["api"] 的三项单价）
        model_name: 模型名（仅用于日志/调试，不参与取价）

    Returns:
        {"hit": float, "miss": float, "output": float}
    """
    pricing = dict(DEFAULT_PRICING)
    try:
        if model_config is not None:
            hit = model_config.get("api", "price_per_million_hit_tokens")
            miss = model_config.get("api", "price_per_million_miss_tokens")
            out = model_config.get("api", "price_per_million_output_tokens")
            # 注意：必须用 is not None 判断，而不是 if hit——合法单价 0 会被 if 真值判定吞掉，
            # 导致 0 单价（免费模型）静默回退到内置默认价，累计费用错误地非 0
            if hit is not None:
                pricing["hit"] = float(hit)
            if miss is not None:
                pricing["miss"] = float(miss)
            if out is not None:
                pricing["output"] = float(out)
    except Exception:
        pass
    if model_name:
        pricing["model"] = model_name
    return pricing


def calculate_cost(hit_tokens: int, miss_tokens: int, output_tokens: int, pricing: dict) -> float:
    """按每百万 token 单价计算费用

    Args:
        hit_tokens: 命中输入 token 数
        miss_tokens: 未命中输入 token 数
        output_tokens: 输出 token 数
        pricing: 包含 hit / miss / output 三项单价（USD / 每百万 token）

    Returns:
        总费用（USD）
    """
    return round(
        (hit_tokens / 1_000_000) * pricing.get("hit", 0)
        + (miss_tokens / 1_000_000) * pricing.get("miss", 0)
        + (output_tokens / 1_000_000) * pricing.get("output", 0),
        6,
    )


class CostTracker:
    """AI 调用成本追踪器

    计费单价从模型配置（ModelConfig）读取，不再硬编码在代码中。
    record() 可接收 model_config 参数传入配置实例；未传入时使用内置默认价。
    """

    def __init__(self, model_config=None):
        self._sessions: Dict[str, list] = {}
        self.model_config = model_config

    def record(self, model: str, hit_tokens: int = 0, miss_tokens: int = 0, output_tokens: int = 0,
               input_tokens: int = 0, session_id: Optional[str] = None,
               model_config=None, pricing: Optional[dict] = None) -> dict:
        """记录一次 API 调用的成本

        Args:
            model: 模型名称
            hit_tokens: 命中缓存输入 token 数
            miss_tokens: 未命中缓存输入 token 数
            output_tokens: 输出 token 数
            input_tokens: (兼容) 总输入 token 数；当 hit/miss 均为 0 时，全部记为未命中
            session_id: 会话 ID（缺省按日期聚合）
            model_config: 模型配置实例（优先），用于读取三项单价
            pricing: 直接传入单价 dict（可选，优先级最高）

        Returns:
            成本记录 dict
        """
        if pricing is None:
            pricing = get_model_pricing(model_config or self.model_config, model)

        # 兼容旧调用：仅提供 input_tokens 时拆分为未命中（视为无缓存命中）
        if hit_tokens == 0 and miss_tokens == 0 and input_tokens > 0:
            miss_tokens = input_tokens
        if miss_tokens < 0:
            miss_tokens = 0

        total_cost = calculate_cost(hit_tokens, miss_tokens, output_tokens, pricing)

        record = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "hit_tokens": hit_tokens,
            "miss_tokens": miss_tokens,
            "output_tokens": output_tokens,
            "input_tokens": hit_tokens + miss_tokens,
            "total_tokens": hit_tokens + miss_tokens + output_tokens,
            "pricing": {k: pricing.get(k) for k in ("hit", "miss", "output")},
            "total_cost": total_cost,
        }

        key = session_id or date.today().isoformat()
        if key not in self._sessions:
            self._sessions[key] = []
        self._sessions[key].append(record)
        return record

    def get_session_cost(self, session_id: str) -> float:
        """获取指定会话的总成本"""
        records = self._sessions.get(session_id, [])
        return round(sum(r["total_cost"] for r in records), 6)

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
        return round(total, 6)

    def get_stats(self) -> Dict:
        """获取汇总统计"""
        total_hit = 0
        total_miss = 0
        total_output = 0
        total_cost = 0.0
        for records in self._sessions.values():
            for r in records:
                total_hit += r["hit_tokens"]
                total_miss += r["miss_tokens"]
                total_output += r["output_tokens"]
                total_cost += r["total_cost"]
        return {
            "total_hit_tokens": total_hit,
            "total_miss_tokens": total_miss,
            "total_output_tokens": total_output,
            "total_tokens": total_hit + total_miss + total_output,
            "total_cost": round(total_cost, 4),
            "session_count": len(self._sessions),
            "default_pricing": DEFAULT_PRICING,
        }

    def reset(self):
        """重置所有记录"""
        self._sessions.clear()