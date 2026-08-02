"""
ModelConfig - 模型配置管理
供应商预设、模型列表、API 配置读写
"""
import json
import os
from pathlib import Path

from config.user_config import USER_DIR, DEFAULTS_DIR, resolve_config_path, load_default_active_model, load_default_api_providers, load_default_chat_config

MODELS_PATH = os.path.join(USER_DIR, "models.json")  # 用户配置主数据源：激活模型配置
DEFAULT_MODELS_PATH = os.path.join(DEFAULTS_DIR, "models.json")  # 默认配置路径（只读）
DEFAULT_API_PROVIDERS_PATH = os.path.join(DEFAULTS_DIR, "api_providers.json")  # API 供应商预设（只读）
DEFAULT_CHAT_PATH = os.path.join(DEFAULTS_DIR, "chat_defaults.json")  # 聊天默认配置（只读）


class ModelConfig:
    """模型配置管理器

    数据源：user_config/user/models.json 中的激活模型（active=true）。
    读取优先 user/ 目录（用户已保存的配置），回退 defaults/ 目录的默认配置。
    默认值统一从 defaults/models.json 读取，不在代码中硬编码。
    """

    def __init__(self):
        self.models_path = Path(MODELS_PATH)
        # 兜底默认模型：从 defaults/models.json 的激活模型读取
        self._fallback = load_default_active_model()
        # 聊天默认配置：从 defaults/chat_defaults.json 读取（stream、system_prompt 等）
        self._chat_defaults = load_default_chat_config()
        self.config = self.load_config()

    def _resolve_models_path(self) -> Path:
        """模型配置读取路径：优先 user/ 目录，回退 defaults/ 目录"""
        return Path(resolve_config_path("models.json"))

    def _get_fallback_value(self, key, default=None):
        """从 defaults 激活模型中取字段值，缺失时返回传入的兜底值"""
        return self._fallback.get(key, default)

    def _load_active_model(self) -> dict:
        """从 models.json 读取激活模型（无 active 时取第一个）
        优先 user/ 目录（用户已保存的配置），回退 defaults/ 目录"""
        path = self._resolve_models_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        models = data.get("models", [])
        if not models:
            return {}
        return next((m for m in models if m.get("active")), models[0])

    def load_config(self):
        """加载配置：优先从 models.json 激活模型组装，无则使用默认配置"""
        model = self._load_active_model()
        if model:
            return self._build_config(model)
        return self.get_default_config()

    def _build_config(self, model: dict) -> dict:
        """根据模型记录组装配置（字段缺失时从 defaults 激活模型读取兜底）"""
        temperature = model.get("temperature", self._get_fallback_value("temperature", 0.7))
        max_tokens = model.get("maxTokens", self._get_fallback_value("maxTokens", 2000))
        return {
            "api": {
                "provider": model.get("provider", self._get_fallback_value("provider")),
                "base_url": model.get("baseUrl", self._get_fallback_value("baseUrl")),
                "api_key": model.get("apiKey", ""),
                "model": model.get("model", self._get_fallback_value("model")),
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            "chat": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": self._chat_defaults.get("stream", True),
                "system_prompt": self._chat_defaults.get("system_prompt", "你是一个有帮助的AI助手。"),
            },
        }

    def get_default_config(self):
        """获取默认配置：从 defaults/models.json 的激活模型读取，不硬编码"""
        return self._build_config(self._fallback)

    def save_config(self):
        """保存配置：写回 user/ 目录的 models.json 激活模型（defaults 不被修改）；
        user 目录无 models.json 时，先复制默认配置再修改"""
        api = self.config.get("api", {})
        read_path = self._resolve_models_path()
        try:
            if read_path.exists():
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                # 从 defaults 复制一份作为用户配置的基础
                default_path = Path(DEFAULT_MODELS_PATH)
                data = json.loads(default_path.read_text(encoding="utf-8")) if default_path.exists() else {"models": []}
            models = data.get("models", [])
            target = next((m for m in models if m.get("active")), models[0] if models else None)
            if target is not None:
                target.update({
                    "provider": api.get("provider", target.get("provider")),
                    "model": api.get("model", target.get("model")),
                    "apiKey": api.get("api_key", target.get("apiKey")),
                    "baseUrl": api.get("base_url", target.get("baseUrl")),
                    "temperature": api.get("temperature", target.get("temperature", self._get_fallback_value("temperature", 0.7))),
                    "maxTokens": api.get("max_tokens", target.get("maxTokens", self._get_fallback_value("maxTokens", 2000))),
                })
            data["models"] = models
            # 写入 user/ 目录（defaults 目录不被修改）
            os.makedirs(os.path.dirname(MODELS_PATH), exist_ok=True)
            with open(MODELS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except (OSError, ValueError) as e:
            print(f"[ModelConfig] ❌ 写回 models.json 失败: {e}")

    def get(self, *keys):
        """获取配置值"""
        value = self.config
        for key in keys:
            value = value.get(key, {})
        return value

    def set(self, *args):
        """设置配置值，最后一个是值，前面的都是键"""
        if len(args) < 2:
            return
        value = args[-1]
        keys = args[:-1]
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def _get_api_providers(self) -> dict:
        """从 defaults/api_providers.json 读取 API 供应商预设表（只读，不硬编码）"""
        return load_default_api_providers()

    def get_provider_info(self, provider_name=None):
        """获取供应商信息：从 defaults/api_providers.json 读取"""
        if provider_name is None:
            provider_name = self.get("api", "provider")
        providers = self._get_api_providers()
        return providers.get(provider_name, providers.get("自定义", {}))

    def get_provider_models(self, provider_name=None):
        """获取供应商的模型列表"""
        info = self.get_provider_info(provider_name)
        return info.get("models", [])

    def get_provider_base_url(self, provider_name=None):
        """获取供应商的 base_url"""
        info = self.get_provider_info(provider_name)
        return info.get("base_url", "")

    def apply_provider(self, provider_name):
        """应用供应商预设（更新 base_url，不清除已有 key）"""
        info = self.get_provider_info(provider_name)
        self.set("api", "provider", provider_name)
        if info["base_url"]:
            self.set("api", "base_url", info["base_url"])
        if info["models"]:
            current_model = self.get("api", "model")
            if current_model not in info["models"]:
                self.set("api", "model", info["models"][0])
