"""
生命周期管理 - 应用启动/停止/重启流程
"""
class LifecycleManager:
    """管理应用生命周期的钩子和状态"""
    def __init__(self):
        self._running = False
        self._hooks = {"startup": [], "shutdown": [], "restart": []}
    
    def register_hook(self, phase: str, handler):
        if phase in self._hooks:
            self._hooks[phase].append(handler)
    
    def startup(self):
        self._running = True
        for h in self._hooks["startup"]:
            h()
        print("[Lifecycle] 应用已启动")
    
    def shutdown(self):
        for h in reversed(self._hooks["shutdown"]):
            h()
        self._running = False
        print("[Lifecycle] 应用已停止")