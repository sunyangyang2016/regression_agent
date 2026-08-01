"""
ModelConfig - 模型配置管理
供应商预设、模型列表、API 配置读写
"""
import json
import yaml
from pathlib import Path

CONFIG_PATH = "user_config/model.yaml"           # 兼容回退（旧单模型配置）
MODELS_PATH = "user_config/defaults/models.json"  # 主数据源：激活模型配置

# API 供应商预设
API_PROVIDERS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-v4-flash", "deepseek-reasoner"]
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    },
    "硅基流动 (SiliconFlow)": {
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct", "meta-llama/Llama-3.3-70B-Instruct"]
    },
    "阿里云 (DashScope)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen2.5-72b-instruct"]
    },
    "智谱 (ZhipuAI)": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-air"]
    },
    "百度 (QianFan)": {
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-4.0", "ernie-3.5-8k", "ernie-speed-128k"]
    },
    "自定义": {
        "base_url": "",
        "models": []
    }
}


class ModelConfig:
    """模型配置管理器

    数据源：user_config/defaults/models.json 中的激活模型（active=true）。
    兼容回退：models.json 不可用时读取旧的 user_config/model.yaml，再回退默认配置。
    """

    def __init__(self):
        self.config_path = Path(CONFIG_PATH)
        self.models_path = Path(MODELS_PATH)
        self.config = self.load_config()

    def _load_active_model(self) -> dict:
        """从 models.json 读取激活模型（无 active 时取第一个）"""
        if not self.models_path.exists():
            return {}
        try:
            with open(self.models_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        models = data.get("models", [])
        if not models:
            return {}
        return next((m for m in models if m.get("active")), models[0])

    def load_config(self):
        """加载配置：优先从 models.json 激活模型组装，其次回退 model.yaml / 默认"""
        model = self._load_active_model()
        if model:
            return {
                "api": {
                    "provider": model.get("provider", "deepseek"),
                    "base_url": model.get("baseUrl", ""),
                    "api_key": model.get("apiKey", ""),
                    "model": model.get("model", "deepseek-chat"),
                    "temperature": model.get("temperature", 0.7),
                    "max_tokens": model.get("maxTokens", 2000),
                },
                "chat": {
                    "temperature": model.get("temperature", 0.7),
                    "max_tokens": model.get("maxTokens", 2000),
                    "stream": True,
                    "system_prompt": "你是一个有帮助的AI助手。",
                },
            }
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or self.get_default_config()
        return self.get_default_config()

    def get_default_config(self):
        """获取默认配置"""
        return {
            "api": {
                "provider": "DeepSeek",
                "base_url": "https://api.deepseek.com",
                "api_key": "",
                "model": "deepseek-chat"
            },
            "chat": {
                "temperature": 0.7,
                "max_tokens": 2048,
                "stream": True,
                "system_prompt": "你是一个有帮助的AI助手。"
            }
        }

    def save_config(self):
        """保存配置：写回 models.json 激活模型；models.json 缺失时回退写 model.yaml"""
        api = self.config.get("api", {})
        if self.models_path.exists():
            try:
                with open(self.models_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                models = data.get("models", [])
                target = next((m for m in models if m.get("active")), models[0] if models else None)
                if target is not None:
                    target.update({
                        "provider": api.get("provider", target.get("provider")),
                        "model": api.get("model", target.get("model")),
                        "apiKey": api.get("api_key", target.get("apiKey")),
                        "baseUrl": api.get("base_url", target.get("baseUrl")),
                        "temperature": api.get("temperature", target.get("temperature", 0.7)),
                        "maxTokens": api.get("max_tokens", target.get("maxTokens", 2000)),
                    })
                data["models"] = models
                with open(self.models_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                return
            except (OSError, ValueError) as e:
                print(f"[ModelConfig] ⚠️ 写回 models.json 失败，回退 model.yaml: {e}")
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)

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

    def get_provider_info(self, provider_name=None):
        """获取供应商信息"""
        if provider_name is None:
            provider_name = self.get("api", "provider")
        return API_PROVIDERS.get(provider_name, API_PROVIDERS["自定义"])

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