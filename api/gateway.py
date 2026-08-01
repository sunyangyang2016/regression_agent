"""
API 网关主类 - 统一暴露 RESTful API
"""
from typing import Any, Dict, Optional
from api.routes import Router
from api.middleware import MiddlewareChain, LoggingMiddleware, CORSMiddleware
from api.auth import AuthManager
from api.rate_limiter import RateLimiter


class APIGateway:
    """API 网关主类"""

    def __init__(self):
        self.router = Router()
        self.auth = AuthManager()
        self.rate_limiter = RateLimiter()
        self.middleware = MiddlewareChain()
        self.middleware.add(LoggingMiddleware())
        self.middleware.add(CORSMiddleware())
        self._handlers: Dict[str, Any] = {}

    def register_handlers(self, handler_obj: Any):
        """注册处理器对象"""
        self._handlers["default"] = handler_obj
        self.router.register_defaults(handler_obj)

    def handle_request(self, path: str, method: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求"""
        request = self.middleware.process_request(request)

        route = self.router.match(path, method)
        if not route:
            return self.middleware.process_response({
                "status": 404,
                "error": f"路由未找到: {method} {path}",
            })

        response = route.handler(request)
        return self.middleware.process_response(response)

    def health(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "version": "0.1.0"}

    def chat(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"response": "API 集成待实现", "conversation_id": ""}

    def tool_call(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "API 集成待实现"}

    def tool_list(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {"tools": []}

    @property
    def routes(self) -> list:
        return [
            {"path": r.path, "method": r.method, "description": r.description}
            for r in self.router.get_all()
        ]