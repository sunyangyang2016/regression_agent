"""pytest 全局配置和共享夹具"""
import os
import sys
import pytest

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_config():
    """示例配置"""
    return {
        "llm_provider": "deepseek",
        "model": "deepseek-chat",
        "temperature": 0.7,
        "context_length": 50,
        "theme": "dark",
    }


@pytest.fixture
def sample_message():
    """示例消息"""
    return {
        "role": "user",
        "content": "你好",
        "timestamp": "2026-07-19T00:00:00",
    }


@pytest.fixture
def sample_model_config():
    """示例模型配置"""
    return {
        "id": "deepseek-chat",
        "provider": "deepseek",
        "name": "DeepSeek Chat",
        "api_key": "sk-test-key",
        "base_url": "https://api.deepseek.com/v1",
        "active": True,
    }