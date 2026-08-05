"""
事件总线 - 模块间异步通信
UI 模块通过事件总线发送请求，业务模块发布结果
支持 asyncio + Qt 信号桥接
"""
from typing import Callable, Dict, List, Any
from PyQt5.QtCore import QObject, pyqtSignal


class EventBusSignals(QObject):
    """Qt 信号桥接 - 用于跨线程事件发送"""
    event_triggered = pyqtSignal(str, object)  # event_name, data


class EventBus:
    """事件总线 - 单例模式，解耦 UI 和业务模块"""
    
    _instance = None
    _signals = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: Dict[str, List[Callable]] = {}
            cls._instance._signals = EventBusSignals()
            cls._instance._signals.event_triggered.connect(cls._instance._on_event_signal)
        return cls._instance
    
    def on(self, event: str, handler: Callable):
        """订阅事件"""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        return self
    
    def off(self, event: str, handler: Callable):
        """取消订阅"""
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h is not handler]
    
    def emit(self, event: str, data: Any = None):
        """发布事件（线程安全 via Qt Signal）"""
        self._signals.event_triggered.emit(event, data)
    
    def _on_event_signal(self, event: str, data: Any):
        """处理信号分发（主线程执行）"""
        handlers = self._handlers.get(event, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                import traceback
                print(f"[EventBus] ❌ 事件处理异常 {event}: {e}")
                traceback.print_exc()
    
    def clear(self):
        """清除所有订阅"""
        self._handlers.clear()
    
    # === 预定义事件名称 ===
    
    # AI 相关
    AI_MESSAGE_SENT = "ai:message_sent"           # 用户发送消息
    AI_CHUNK_RECEIVED = "ai:chunk_received"       # 流式块到达
    AI_RESPONSE_COMPLETE = "ai:response_complete" # AI 回复完成
    AI_ERROR = "ai:error"                         # AI 错误
    AI_TOOL_CALL = "ai:tool_call"                 # AI 调用工具
    AI_TOOL_RESULT = "ai:tool_result"             # 工具调用结果
    AI_ROUND_RECEIVED = "ai:round_received"       # AI 每轮最终回复到达
    
    # MCP 相关
    MCP_PLUGIN_INSTALL = "mcp:plugin_install"     # 安装插件
    MCP_PLUGIN_UNINSTALL = "mcp:plugin_uninstall" # 卸载插件
    MCP_PLUGIN_INSTALLED = "mcp:plugin_installed" # 安装完成
    MCP_REMOTE_ADD = "mcp:remote_add"            # 添加远程
    MCP_REMOTE_REMOVE = "mcp:remote_remove"      # 移除远程
    MCP_CONFIG_SAVE = "mcp:config_save"          # 保存配置
    
    # Skill 相关
    SKILL_ADD = "skill:add"                       # 添加技能
    SKILL_REMOVE = "skill:remove"                 # 删除技能
    SKILL_TOGGLE = "skill:toggle"                 # 切换技能
    SKILL_UPDATED = "skill:updated"               # 技能更新完成
    
    # UI 相关
    UI_TAB_SWITCH = "ui:tab_switch"               # 切换标签
    UI_CONFIG_CHANGED = "ui:config_changed"       # 配置变更
    UI_THEME_CHANGED = "ui:theme_changed"         # 主题变更
    UI_PLUGIN_REGISTERED = "ui:plugin_registered" # 插件注册
    
    # 系统
    SYS_CONNECTED = "sys:connected"               # AI 连接成功
    SYS_DISCONNECTED = "sys:disconnected"         # AI 断开
    SYS_ERROR = "sys:error"                       # 系统错误