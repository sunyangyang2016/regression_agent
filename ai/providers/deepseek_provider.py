"""
DeepSeek 供应商实现
"""
from .base_provider import BaseProvider


class DeepSeekProvider(BaseProvider):
    def create_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            base_url=self.config.get("base_url", "https://api.deepseek.com"),
            api_key=self.config.get("api_key", "")
        )
    
    async def stream_chat(self, messages, tools=None, **kwargs):
        client = self.create_client()
        async for chunk in await client.chat.completions.create(
            model=self.config.get("model", "deepseek-chat"),
            messages=messages,
            tools=tools,
            stream=True,
            **kwargs
        ):
            yield chunk