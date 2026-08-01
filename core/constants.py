"""
系统常量定义
"""
APP_NAME = "Regression Agent"
APP_VERSION = "0.1.0"
APP_AUTHOR = "Regression"

# 事件名称常量
EVENT_AI_MESSAGE_SENT = "ai:message_sent"
EVENT_AI_CHUNK_RECEIVED = "ai:chunk_received"
EVENT_AI_RESPONSE_COMPLETE = "ai:response_complete"
EVENT_TOOL_CALL = "tool:call"
EVENT_TOOL_RESULT = "tool:result"
EVENT_SKILL_ACTIVATED = "skill:activated"
EVENT_PLUGIN_LOADED = "plugin:loaded"

# 默认配置
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MODEL = "deepseek-chat"

# 路径
CONFIG_DIR = "config"
DATA_DIR = "data"
LOGS_DIR = "logs"