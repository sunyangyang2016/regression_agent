"""
用户配置管理 - 从 user_config/defaults/ 加载默认配置
"""
import json
import os

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULTS_DIR = os.path.join(CONFIG_DIR, "defaults")


def _read_json(name: str) -> dict:
    """读取默认 JSON 配置文件"""
    path = os.path.join(DEFAULTS_DIR, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_app_info() -> dict:
    """加载应用信息"""
    return _read_json("app_info.json")


def load_default_models() -> list:
    """加载默认模型列表"""
    return _read_json("models.json").get("models", [])


def load_default_mcp_servers() -> list:
    """加载默认 MCP 服务器列表"""
    return _read_json("mcp_servers.json").get("servers", [])


def load_default_mcp_market() -> list:
    """加载默认 MCP 市场列表"""
    return _read_json("mcp_market.json").get("market", [])


def load_default_skills() -> list:
    """加载默认技能列表"""
    return _read_json("skills.json").get("skills", [])


def load_all_defaults() -> dict:
    """加载所有默认配置"""
    return {
        "app_info": load_app_info(),
        "defaultModels": load_default_models(),
        "defaultMCPServers": load_default_mcp_servers(),
        "defaultMCPMarket": load_default_mcp_market(),
        "defaultSkills": load_default_skills(),
    }