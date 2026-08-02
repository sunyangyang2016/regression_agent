"""AgentConfigBridge - Agent 配置桥接（主题等应用级配置）"""
import json
import os
from PyQt5.QtCore import pyqtSlot
from .base import BridgeBase
from config.user_config import USER_DIR, DEFAULTS_DIR, resolve_config_path

AGENT_CONFIG_FILENAME = "agent_config.json"


class AgentConfigBridge(BridgeBase):
    """配置优先级：user/ > defaults/；用户保存写入 user/，defaults/ 不被修改"""

    @pyqtSlot(result=str)
    def getConfig(self):
        try:
            path = resolve_config_path(AGENT_CONFIG_FILENAME)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return json.dumps(self._default(), ensure_ascii=False)
        except Exception as e:
            print(f"[AgentConfigBridge] 读取失败: {e}")
            return json.dumps(self._default(), ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def saveConfig(self, config_json):
        try:
            cfg = json.loads(config_json) if isinstance(config_json, str) else config_json
            os.makedirs(USER_DIR, exist_ok=True)
            path = os.path.join(USER_DIR, AGENT_CONFIG_FILENAME)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(f"[AgentConfigBridge] 已保存 → {path}")
            return True
        except Exception as e:
            print(f"[AgentConfigBridge] 保存失败: {e}")
            return False

    def _default(self):
        d = os.path.join(DEFAULTS_DIR, AGENT_CONFIG_FILENAME)
        if os.path.exists(d):
            try:
                with open(d, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"theme": "dark"}