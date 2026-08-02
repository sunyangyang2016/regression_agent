"""
AIController - AI 通信控制器
管理 AI 客户端的连接、消息发送、流式响应、工具调用
"""
from PyQt5.QtCore import QObject, pyqtSignal


class AIController(QObject):
    """AI 通信控制器 — 管理 AI 客户端的连接与通信"""

    connection_changed = pyqtSignal(bool, str)
    stream_chunk = pyqtSignal(str)
    stream_complete = pyqtSignal(str)
    stream_error = pyqtSignal(str)
    tool_call_received = pyqtSignal(str, str, str)
    raw_log = pyqtSignal(str)  # 底层 AI 通信原始 JSON 日志（request/response）

    def __init__(self, ai_client, model_config, parent=None):
        super().__init__(parent)
        self.ai_client = ai_client
        self.model_config = model_config
        self.messages = self._get_initial_messages()
        self._connected = False
        self._stream_buffer = ""
        # 将底层原始日志回调注入到 AIClient
        self.ai_client.on_raw_log = self._on_raw_log

    def _on_raw_log(self, raw_json: str):
        """接收底层 AI 通信原始 JSON 日志并从 Qt 信号发出去"""
        self.raw_log.emit(raw_json)

    def _get_initial_messages(self):
        system_prompt = self.model_config.get("chat", "system_prompt")
        if not system_prompt:
            system_prompt = "You are a helpful assistant."
        return [{"role": "system", "content": system_prompt}]

    @property
    def connected(self):
        return self._connected

    def connect(self):
        success, msg = self.ai_client.connect()
        self._connected = success
        self.connection_changed.emit(success, msg)
        return success, msg

    def reconnect(self):
        """热重连：不重启事件循环，只更换配置和 StreamHandler"""
        success, msg = self.ai_client.reconnect()
        self._connected = success
        self._stream_buffer = ""
        self.connection_changed.emit(success, msg)
        return success, msg

    def send_message(self, content, extra_messages=None):
        if not self._connected:
            self.stream_error.emit("AI 客户端未连接，请检查配置")
            return
        self._stream_buffer = ""
        self.messages.append({"role": "user", "content": content})
        self.ai_client.send_message(
            messages=self.messages,
            content=content,
            on_chunk=self._on_chunk,
            on_complete=self._on_complete,
            on_error=self._on_error,
            on_tool_call=self._on_tool_call
        )

    def _on_chunk(self, chunk):
        self._stream_buffer += chunk
        self.stream_chunk.emit(self._stream_buffer)

    def _on_complete(self, full_response):
        self._stream_buffer = full_response
        self.messages.append({"role": "assistant", "content": full_response})
        self.stream_complete.emit(full_response)

    def _on_error(self, error_msg):
        self.stream_error.emit(error_msg)

    def _on_tool_call(self, tool_name, arguments, result):
        import json
        args_json = json.dumps(arguments) if isinstance(arguments, (dict, list)) else str(arguments)
        self.tool_call_received.emit(tool_name, args_json, result or "")

    def inject_context(self, context_text: str):
        if self.messages and self.messages[0]["role"] == "system":
            system_prompt = self.model_config.get("chat", "system_prompt")
            self.messages[0] = {"role": "system", "content": system_prompt + context_text}

    def reset_messages(self):
        self.messages = self._get_initial_messages()
        self._stream_buffer = ""

    def cleanup(self):
        try:
            self.ai_client.cleanup()
        except Exception:
            pass