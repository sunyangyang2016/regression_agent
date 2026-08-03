"""安全插件模型层 - 读写 config/security_config.json"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "security_config.json")


def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:
        print(f"[SecurityModel] [WARN] 读取配置失败: {e}")
    return {}


def save_config(cfg: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg or {}, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"[SecurityModel] [ERROR] 保存配置失败: {e}")
        return False