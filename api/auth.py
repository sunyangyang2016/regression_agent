"""
API 认证授权
"""
import hashlib
import time
from typing import Any, Dict, Optional, Set


class AuthManager:
    """API 认证管理器"""

    def __init__(self):
        self._api_keys: Dict[str, str] = {}     # key -> user_id
        self._tokens: Dict[str, float] = {}     # token -> expiry
        self._token_ttl = 3600  # 1 hour

    def add_api_key(self, key: str, user_id: str):
        """添加 API Key"""
        self._api_keys[key] = user_id

    def remove_api_key(self, key: str):
        """移除 API Key"""
        self._api_keys.pop(key, None)

    def validate_api_key(self, key: str) -> Optional[str]:
        """验证 API Key，返回用户 ID"""
        return self._api_keys.get(key)

    def generate_token(self, user_id: str) -> str:
        """生成访问令牌"""
        raw = f"{user_id}:{time.time()}:{hashlib.md5(user_id.encode()).hexdigest()}"
        token = hashlib.sha256(raw.encode()).hexdigest()
        self._tokens[token] = time.time() + self._token_ttl
        return token

    def validate_token(self, token: str) -> bool:
        """验证访问令牌"""
        expiry = self._tokens.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._tokens[token]
            return False
        return True

    def revoke_token(self, token: str):
        """撤销访问令牌"""
        self._tokens.pop(token, None)

    def clean_expired(self):
        """清理过期令牌"""
        now = time.time()
        expired = [k for k, v in self._tokens.items() if now > v]
        for k in expired:
            del self._tokens[k]