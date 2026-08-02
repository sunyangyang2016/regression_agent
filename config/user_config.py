"""
用户配置读写工具
默认配置目录：user_config/defaults/（只读，永不修改）
用户配置目录：user_config/user/（优先读取，写入时自动创建）
读取优先级：user/ > defaults/
"""
import json
import os

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_config")
DEFAULTS_DIR = os.path.join(CONFIG_DIR, "defaults")
USER_DIR = os.path.join(CONFIG_DIR, "user")


def _read_json(name: str, base_dir: str = None) -> dict:
    """读取指定目录下的 JSON 配置文件"""
    path = os.path.join(base_dir or DEFAULTS_DIR, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def resolve_config_path(name: str) -> str:
    """解析配置文件的读取路径：优先 user/ 目录，回退 defaults/ 目录

    用户目录下存在该文件 -> 返回 user 目录路径
    否则返回 defaults 目录路径（defaults 目录内容永不被修改）
    """
    user_path = os.path.join(USER_DIR, name)
    if os.path.exists(user_path):
        return user_path
    return os.path.join(DEFAULTS_DIR, name)


def read_config(name: str) -> dict:
    """读取配置：优先 user/ 目录（用户已保存的个性化配置），
    若不存在则回退读取 defaults/ 目录的默认配置"""
    return _read_json(name, base_dir=USER_DIR) or _read_json(name, base_dir=DEFAULTS_DIR)


def save_config(name: str, data: dict) -> str:
    """保存配置到 user/ 目录（自动创建目录），defaults/ 目录永不被修改

    返回写入的文件路径
    """
    os.makedirs(USER_DIR, exist_ok=True)
    path = os.path.join(USER_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return path


def load_agent_info() -> dict:
    """加载 Agent 信息（关于界面详情，defaults/agent_info.json）"""
    return _read_json("agent_info.json")


def load_default_models() -> list:
    """加载默认模型列表（defaults/models.json）"""
    return _read_json("models.json").get("models", [])


def load_default_active_model() -> dict:
    """加载 defaults/models.json 中的激活模型（无 active 标记时取第一个）
    作为字段缺失时的兜底默认值，统一从 defaults 目录读取，不硬编码在代码中"""
    models = load_default_models()
    if not models:
        return {}
    return next((m for m in models if m.get("active")), models[0])


def load_default_api_providers() -> dict:
    """加载 defaults/api_providers.json 中的 API 供应商预设表"""
    return _read_json("api_providers.json").get("providers", {})


def load_default_chat_config() -> dict:
    """加载 defaults/chat_defaults.json 中的聊天默认配置（stream、system_prompt 等）"""
    return _read_json("chat_defaults.json")