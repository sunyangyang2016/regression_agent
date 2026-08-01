"""
Controller 层
"""
from .bridge_manager import BridgeManager
from .bridge_loader import BridgeLoader
from .chat_controller import ChatController
from .app_controller import AppController

__all__ = ["BridgeManager", "BridgeLoader", "ChatController", "AppController"]

# 桥接逻辑已迁移到 bridge/ 目录
from bridge import ChatBridge, ModelBridge, ToolBridge, SkillBridge, MCPBridge