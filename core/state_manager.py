"""
全局状态管理
"""
class StateManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._state = {}
        return cls._instance
    
    def get(self, key, default=None):
        return self._state.get(key, default)
    
    def set(self, key, value):
        self._state[key] = value
    
    def clear(self):
        self._state.clear()