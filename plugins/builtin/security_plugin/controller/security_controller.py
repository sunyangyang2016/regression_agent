"""安全插件控制器层 - 配置读写业务逻辑"""
from ..model import security_model


def get_config() -> dict:
    return security_model.load_config()


def save_config(cfg: dict) -> bool:
    return security_model.save_config(cfg)