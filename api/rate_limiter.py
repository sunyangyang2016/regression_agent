"""
API 限流器 - 请求频率限制
"""
import time
from typing import Dict, Optional, Tuple
from collections import defaultdict


class RateLimiter:
    """请求频率限制器"""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

    def check(self, key: str) -> Tuple[bool, int]:
        """检查请求是否允许，返回 (允许, 剩余请求数)"""
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        remaining = self.max_requests - len(self._requests[key])
        if remaining <= 0:
            return False, 0

        self._requests[key].append(now)
        return True, remaining - 1

    def reset(self, key: Optional[str] = None):
        """重置限流"""
        if key:
            self._requests.pop(key, None)
        else:
            self._requests.clear()

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        return max(0, self.max_requests - len(self._requests[key]))