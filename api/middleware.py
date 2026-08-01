"""
API 中间件
"""
import time
from typing import Any, Callable, Dict, List


class Middleware:
    """API 中间件基类"""

    def before_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """请求前处理"""
        return request

    def after_request(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """响应后处理"""
        return response


class LoggingMiddleware(Middleware):
    """日志中间件"""
    def before_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request["_start_time"] = time.time()
        return request

    def after_request(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response


class CORSMiddleware(Middleware):
    """CORS 中间件"""
    def __init__(self, origins: List[str] = None):
        self.origins = origins or ["*"]

    def after_request(self, response: Dict[str, Any]) -> Dict[str, Any]:
        response["headers"] = {
            "Access-Control-Allow-Origin": ", ".join(self.origins),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
        return response


class MiddlewareChain:
    """中间件链"""

    def __init__(self):
        self._middlewares: List[Middleware] = []

    def add(self, middleware: Middleware):
        self._middlewares.append(middleware)

    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        for m in self._middlewares:
            request = m.before_request(request)
        return request

    def process_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        for m in self._middlewares:
            response = m.after_request(response)
        return response