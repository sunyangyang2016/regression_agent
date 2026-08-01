"""
API 路由定义
"""
from typing import Any, Callable, Dict, List, Optional


class Route:
    """路由定义"""
    def __init__(self, path: str, method: str, handler: Callable, description: str = ""):
        self.path = path
        self.method = method.upper()
        self.handler = handler
        self.description = description


class Router:
    """路由管理器"""

    def __init__(self):
        self._routes: List[Route] = []

    def get(self, path: str, description: str = ""):
        """注册 GET 路由"""
        def decorator(handler):
            self._routes.append(Route(path, "GET", handler, description))
            return handler
        return decorator

    def post(self, path: str, description: str = ""):
        """注册 POST 路由"""
        def decorator(handler):
            self._routes.append(Route(path, "POST", handler, description))
            return handler
        return decorator

    def add_route(self, path: str, method: str, handler: Callable, description: str = ""):
        """添加路由"""
        self._routes.append(Route(path, method, handler, description))

    def match(self, path: str, method: str) -> Optional[Route]:
        """匹配路由"""
        method = method.upper()
        for route in self._routes:
            if route.path == path and route.method == method:
                return route
        return None

    def get_all(self) -> List[Route]:
        """获取所有路由"""
        return list(self._routes)

    def clear(self):
        """清空路由"""
        self._routes.clear()

    def register_defaults(self, handler_obj: Any):
        """注册默认路由"""
        self.get("/health", "健康检查")(handler_obj.health)
        self.post("/chat", "聊天")(handler_obj.chat)
        self.post("/tools/call", "工具调用")(handler_obj.tool_call)
        self.get("/tools/list", "工具列表")(handler_obj.tool_list)