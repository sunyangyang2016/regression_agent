"""
AppStateManager - 应用状态管理
"""
from PyQt5.QtCore import QObject, pyqtSignal


class AppStateManager(QObject):
    """应用状态管理"""

    state_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = {}

    def get(self, key: str, default=None):
        return self._states.get(key, default)

    def set(self, key: str, value):
        old = self._states.get(key)
        if old != value:
            self._states[key] = value
            self.state_changed.emit(key, value)

    def update(self, data: dict):
        for key, value in data.items():
            self._states[key] = value
            self.state_changed.emit(key, value)

    def keys(self):
        return self._states.keys()

    def items(self):
        return self._states.items()

    def __contains__(self, key):
        return key in self._states