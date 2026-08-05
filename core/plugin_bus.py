"""
core/plugin_bus.py —— 插件生态跨层通用通信总线
生产者（如 MCPDispatcher）发布事件，插件订阅事件，双方零直接依赖。
"""
import threading


class PluginBus:
    """通用事件总线（类级静态，跨层共享）"""

    _listeners = {}                 # event -> [callback, ...]
    _lock = threading.Lock()        # 跨线程安全

    @classmethod
    def subscribe(cls, event: str, callback):
        """订阅事件（插件侧调用）"""
        with cls._lock:
            lst = cls._listeners.setdefault(event, [])
            if callback not in lst:
                lst.append(callback)

    @classmethod
    def unsubscribe(cls, event: str, callback):
        """取消订阅"""
        with cls._lock:
            lst = cls._listeners.get(event, [])
            if callback in lst:
                lst.remove(callback)

    @classmethod
    def publish(cls, event: str, *args, **kwargs):
        """发布事件（生产者侧调用）；单订阅者异常不阻断其他订阅者"""
        with cls._lock:
            targets = list(cls._listeners.get(event, []))
        for cb in targets:
            try:
                cb(*args, **kwargs)
            except Exception as e:
                print(f"[PluginBus] 回调失败({event}): {e}")