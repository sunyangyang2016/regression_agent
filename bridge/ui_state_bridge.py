"""UIStateBridge - UI 状态桥接（面板开合、侧边栏、插件 Tab 等界面状态持久化）

UI 状态保存到 user_config/user/ui_state.json，defaults/ 提供默认值。
前端在界面状态变化时调用 saveState，启动时调用 getState 恢复。
"""
import json
import os
from PyQt5.QtCore import pyqtSlot
from .base import BridgeBase
from config.user_config import USER_DIR, DEFAULTS_DIR

UI_STATE_FILENAME = "ui_state.json"


class UIStateBridge(BridgeBase):
    """配置优先级：user/ > defaults/；用户状态写入 user/，defaults/ 不被修改"""

    @pyqtSlot(result=str)
    def getState(self):
        try:
            user_path = os.path.join(USER_DIR, UI_STATE_FILENAME)
            if os.path.exists(user_path):
                with open(user_path, "r", encoding="utf-8") as f:
                    return f.read()
            default_path = os.path.join(DEFAULTS_DIR, UI_STATE_FILENAME)
            if os.path.exists(default_path):
                with open(default_path, "r", encoding="utf-8") as f:
                    return f.read()
            return json.dumps(self._default(), ensure_ascii=False)
        except Exception as e:
            print(f"[UIStateBridge] 读取失败: {e}")
            return json.dumps(self._default(), ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def saveState(self, state_json):
        try:
            state = json.loads(state_json) if isinstance(state_json, str) else state_json
            os.makedirs(USER_DIR, exist_ok=True)
            path = os.path.join(USER_DIR, UI_STATE_FILENAME)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"[UIStateBridge] 已保存 → {path}")
            return True
        except Exception as e:
            print(f"[UIStateBridge] 保存失败: {e}")
            return False

    def _default(self):
        d = os.path.join(DEFAULTS_DIR, UI_STATE_FILENAME)
        if os.path.exists(d):
            try:
                with open(d, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "sidebarCollapsed": False,
            "panelOpen": False,
            "currentTab": "mcp",
            "mcpSubTab": "market",
            "openPlugins": [],
            "activePluginTab": "chat",
        }
