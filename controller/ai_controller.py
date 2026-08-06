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
    stream_cancelled = pyqtSignal(str)  # AI 流被用户中断（携带已生成的部分内容）
    tool_call_received = pyqtSignal(str, str, str)
    raw_log = pyqtSignal(str)  # 底层 AI 通信原始 JSON 日志（request/response）
    progress_usage = pyqtSignal(str)  # 多轮工具调用中间进度 token（JSON 字符串）
    round_received = pyqtSignal(str)  # AI 每轮最终回复数据（JSON 字符串：round/marker/text）

    def __init__(self, ai_client, model_config, parent=None):
        super().__init__(parent)
        self.ai_client = ai_client
        self.model_config = model_config
        self.messages = self._get_initial_messages()
        self._connected = False
        self._stream_buffer = ""
        # 生成令牌：每次 send_message / reset_messages 递增。
        # 回调（chunk/complete/error）携带发起时的令牌，若令牌不匹配则丢弃，
        # 防止会话切换后旧 AI 任务的回调污染新会话的 messages（→「会话串了」）
        self._generation_token = 0
        # 将底层原始日志回调注入到 AIClient
        self.ai_client.on_raw_log = self._on_raw_log
        # 注入中间进度 token 回调
        self.ai_client.on_progress_usage = self._on_progress_usage

    def _on_raw_log(self, raw_json: str):
        """接收底层 AI 通信原始 JSON 日志并从 Qt 信号发出去"""
        self.raw_log.emit(raw_json)

    def _on_progress_usage(self, usage_json):
        self.progress_usage.emit(usage_json)

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

    def stop_streaming(self):
        """中断当前正在进行的 AI 流式回复"""
        if self._connected and self.ai_client:
            self.ai_client.cancel_current()
            print("[AIController] ⏹ 已请求中断 AI 流式回复")
            # 将已生成的流缓冲作为部分内容发出
            self.stream_cancelled.emit(self._stream_buffer or "")
        else:
            self.stream_cancelled.emit("")

    def send_message(self, content, extra_messages=None):
        if not self._connected:
            self.stream_error.emit("AI 客户端未连接，请检查配置")
            return
        self._stream_buffer = ""
        # 注意：不要在此处 append 用户消息！
        # AIClient.send_message 会执行 self.messages = messages（引用同步），
        # 随后 send_message_async 内部会统一 append {"role": "user", "content": content}。
        # 若此处再 append 一次，用户消息会重复出现在发给 AI 的 messages 中。
        self._generation_token += 1
        my_token = self._generation_token

        def _on_chunk(chunk):
            """分片回调：带生成令牌校验，防止跨会话污染"""
            if self._generation_token != my_token:
                return
            self._stream_buffer += chunk
            self.stream_chunk.emit(self._stream_buffer)

        def _on_complete(full_response):
            """完成回调：带生成令牌校验，防止跨会话污染 messages"""
            if self._generation_token != my_token:
                return
            self._stream_buffer = full_response
            self.messages.append({"role": "assistant", "content": full_response})
            self.stream_complete.emit(full_response)

        def _on_error(error_msg):
            """错误回调：带生成令牌校验"""
            if self._generation_token != my_token:
                return
            self.stream_error.emit(error_msg)

        def _on_tool_call(tool_name, arguments, result):
            """工具调用回调：带生成令牌校验"""
            if self._generation_token != my_token:
                return
            import json
            args_json = json.dumps(arguments) if isinstance(arguments, (dict, list)) else str(arguments)
            self.tool_call_received.emit(tool_name, args_json, result or "")

        def _on_round(round_data):
            """每轮最终回复回调：带生成令牌校验"""
            if self._generation_token != my_token:
                return
            import json
            try:
                if isinstance(round_data, dict):
                    payload = round_data
                else:
                    payload = json.loads(round_data)
                self.round_received.emit(json.dumps(payload, ensure_ascii=False))
            except Exception as e:
                print(f"[AIController] ⚠️ round 数据序列化失败: {e}")

        self.ai_client.send_message(
            messages=self.messages,
            content=content,
            on_chunk=_on_chunk,
            on_complete=_on_complete,
            on_error=_on_error,
            on_tool_call=_on_tool_call,
            on_round=_on_round
        )

    def inject_context(self, context_text: str):
        if self.messages and self.messages[0]["role"] == "system":
            system_prompt = self.model_config.get("chat", "system_prompt")
            self.messages[0] = {"role": "system", "content": system_prompt + context_text}

    def compress_context(self, strategy="truncate"):
        """手动压缩当前会话上下文（用户主动触发）

        Returns:
            dict: 压缩统计信息（{triggered, before_tokens, after_tokens, ...}）
        """
        try:
            from ai.context_window import ContextWindowManager
            max_ctx = self.model_config.get("api", "max_context") or 65536
            mgr = ContextWindowManager(max_context=max_ctx)
            new_messages, stats = mgr.compress(self.messages, strategy=strategy)
            if stats.get("triggered"):
                self.messages = new_messages
                print(f"[ContextWindow] ⏳ 手动压缩完成: {stats['before_tokens']} → "
                      f"{stats['after_tokens']} tokens, 压缩 {stats['compressed_units']} 个旧对话单元")
            return stats
        except Exception as e:
            print(f"[ContextWindow] ❌ 手动压缩失败: {e}")
            return {"triggered": False, "error": str(e)}

    def reset_messages(self):
        # 递增生成令牌：使旧 AI 任务的回调全部失效（防止旧回复写入新消息列表）
        self._generation_token += 1
        self.messages = self._get_initial_messages()
        self._stream_buffer = ""

    def cleanup(self):
        try:
            self.ai_client.cleanup()
        except Exception:
            pass