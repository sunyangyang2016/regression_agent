"""
供应商工厂 - 根据配置创建对应AI供应商实例
"""
from .base_provider import BaseProvider


class ProviderFactory:
    _providers = {}
    
    @classmethod
    def register(cls, name: str, provider_class):
        cls._providers[name] = provider_class
    
    @classmethod
    def create(cls, name: str, config: dict = None) -> BaseProvider:
        provider_class = cls._providers.get(name)
        if not provider_class:
            raise ValueError(f"未知供应商: {name}")
        return provider_class(config)


# 注册内建供应商
from .openai_provider import OpenAIProvider
from .deepseek_provider import DeepSeekProvider
ProviderFactory.register("openai", OpenAIProvider)
ProviderFactory.register("deepseek", DeepSeekProvider)