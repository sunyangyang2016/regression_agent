"""
AI供应商基类 - 策略模式
"""
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """AI供应商抽象基类"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    @abstractmethod
    def create_client(self):
        pass
    
    @abstractmethod
    async def stream_chat(self, messages, tools=None, **kwargs):
        pass