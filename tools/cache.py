"""
工具结果缓存
"""
import time
import hashlib
import json
from typing import Any, Dict, Optional, Tuple


class ToolCache:
    """工具结果缓存"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

    def _make_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """生成缓存键"""
        content = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """获取缓存结果"""
        key = self._make_key(tool_name, args)
        if key not in self._cache:
            return None
        result, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            del self._cache[key]
            return None
        return result

    def set(self, tool_name: str, args: Dict[str, Any], result: Any):
        """设置缓存"""
        key = self._make_key(tool_name, args)
        self._cache[key] = (result, time.time())
        if len(self._cache) > self.max_size:
            self._evict_oldest()

    def invalidate(self, tool_name: Optional[str] = None):
        """失效缓存"""
        if tool_name is None:
            self._cache.clear()
        else:
            keys_to_delete = [
                k for k in self._cache.keys()
                if k.startswith(hashlib.md5(tool_name.encode()).hexdigest()[:8])
            ]
            for k in keys_to_delete:
                del self._cache[k]

    def _evict_oldest(self):
        """淘汰最旧条目"""
        if not self._cache:
            return
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
        del self._cache[oldest_key]

    @property
    def size(self) -> int:
        return len(self._cache)