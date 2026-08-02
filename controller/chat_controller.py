"""
ChatController - 聊天控制器
接收用户交互事件，调用 Model 更新数据，决定 View 如何刷新
"""
import json
import threading
from PyQt5.QtCore import QObject, pyqtSignal

LOG = "[ChatController]"


class ChatController(QObject):
    """聊天控制器"""

    update_message = pyqtSignal(str, str)
    complete_message = pyqtSignal(str)
    set_processing = pyqtSignal(bool)
    show_error = pyqtSignal(str)
    add_tool_call = pyqtSignal(str, str)
    token_update = pyqtSignal(str)
    log_entry = pyqtSignal(str)

    def __init__(self, ai_controller, conversation_model, model_config, parent=None):
        super().__init__(parent)
        self.ai_controller = ai_controller
        self.conversation_model = conversation_model
        self.model_config = model_config
        self.bridge = None
        self._first_reply = True
        self._token_counter = None
        self._cost_tracker = None
        self._session_total_tokens = 0
        self._session_total_cost = 0.0

        self.ai_controller.stream_chunk.connect(self._on_stream_chunk)
        self.ai_controller.stream_complete.connect(self._on_stream_complete)
        self.ai_controller.stream_error.connect(self._on_stream_error)
        self.ai_controller.tool_call_received.connect(self._on_tool_call)
        self.token_update.connect(self._on_token_update)
        self.log_entry.connect(self._on_log_entry)

    def set_bridge(self, bridge):
        self.bridge = bridge

    def handle_user_message(self, content: str):
        if not content.strip():
            return
        if not self.ai_controller.connected:
            self.show_error.emit("AI 客户端未连接，请检查配置")
            self.complete_message.emit("")
            return

        self.conversation_model.ensure_conversation(
            self.model_config.get("api", "model") or "deepseek-chat"
        )

        is_first = not bool(self.conversation_model.current_user_content)
        self.conversation_model.current_user_content = content
        self.conversation_model.save_message("user", content)
        if is_first:
            self._first_reply = True

        self.set_processing.emit(True)
        self.update_message.emit("", "⏳ 思考中…")

        def do_ai_call():
            try:
                # 在后台线程注入 MCP 上下文，避免主线程与 MCP 后台加载线程
                # 并发读写 MCPHost._clients（可能导致 UI 卡顿或字典迭代异常）
                self._inject_mcp_context()
                self.ai_controller.send_message(content)
            except Exception as ex:
                print(f"{LOG} ❌ AI 调用异常: {ex}")
                self.show_error.emit(str(ex))
                self.complete_message.emit("")

        threading.Thread(target=do_ai_call, daemon=True).start()

    def handle_load_conversation(self, conversation_id: str):
        messages = self.conversation_model.load_conversation_messages(conversation_id)
        self.ai_controller.reset_messages()
        # 从数据库加载已保存的 token 数据
        self._session_total_tokens = self.conversation_model.get_token_count(conversation_id)
        # 累计费用由累计 token 推导，确保 UI 上费用与 token 同步显示
        self._session_total_cost = self._calculate_session_cost(self._session_total_tokens)
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "user":
                self.ai_controller.messages.append({"role": "user", "content": content})
            elif role == "assistant":
                self.ai_controller.messages.append({"role": "assistant", "content": content})

        msgs_json = json.dumps(messages, ensure_ascii=False)
        if self.bridge:
            self.bridge.execute_js(f"loadConversationMessages({msgs_json});")
            # 恢复会话的 token 统计显示
            max_ctx = 8192
            ctx_pct = (self._session_total_tokens / max_ctx) * 100
            self.push_token_stats(self._session_total_tokens, 0, 0, ctx_pct, self._session_total_cost, max_ctx)

    def _calculate_session_cost(self, tokens: int) -> float:
        """根据累计 token 数计算累计费用（费用数据由 token 推导，保证 UI 同步）

        费用 = (累计 token / 1000) × 模型输出单价
        """
        model_name = self.model_config.get("api", "model") or "deepseek-chat"
        from ai.cost_tracker import MODEL_PRICING
        pricing = MODEL_PRICING.get(model_name, {"input": 0.001, "output": 0.002})
        return round((tokens / 1000) * pricing["output"], 4)

    def _on_stream_chunk(self, content: str):
        self.update_message.emit("", content)

    def _on_stream_complete(self, full_response: str):
        # 尝试从流式响应中提取 OpenAI SDK 返回的精确 token 数和真实内容
        user_content = self.conversation_model.current_user_content or ""
        input_tokens = 0
        output_tokens = 0
        content = full_response

        if full_response.startswith('{"content"'):
            try:
                parsed = json.loads(full_response)
                usage = parsed.get("_usage", {})
                if usage:
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                content = parsed.get("content", full_response)
            except Exception:
                pass

        # 使用提取的真实内容保存和显示
        self.conversation_model.save_message("assistant", content)
        self.update_message.emit("", content)
        self.complete_message.emit("")
        self.set_processing.emit(False)

        if input_tokens == 0 and output_tokens == 0:
            from ai.token_counter import TokenCounter
            input_tokens = TokenCounter.count_text(user_content)
            output_tokens = TokenCounter.count_text(content)

        round_tokens = output_tokens
        self._session_total_tokens += round_tokens

        max_ctx = 8192
        ctx_pct = (self._session_total_tokens / max_ctx) * 100

        # 累计费用由累计 token 推导，确保 UI 上费用与 token 同步刷新
        model_name = self.model_config.get("api", "model") or "deepseek-chat"
        self._session_total_cost = self._calculate_session_cost(self._session_total_tokens)

        # 保存 token 数到数据库
        self.conversation_model.update_token_count(self._session_total_tokens)

        self.push_token_stats(self._session_total_tokens, input_tokens, output_tokens, ctx_pct, self._session_total_cost, max_ctx)
        self.push_log_entry(
            model=model_name,
            request=user_content,
            response=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        # 首条回复完成后更新标题（基于用户第一条消息）
        if self._first_reply:
            self._first_reply = False
            content = self.conversation_model.current_user_content
            if content:
                self.conversation_model.update_title(content)
                self.sync_conversations_to_view()

    def _on_stream_error(self, error_msg: str):
        self.update_message.emit("", f"❌ {error_msg}")
        self.complete_message.emit("")
        self.set_processing.emit(False)

    def _on_tool_call(self, tool_name: str, arguments_json: str, result: str):
        if self.bridge:
            try:
                if isinstance(arguments_json, str):
                    try:
                        args = json.loads(arguments_json)
                        args_str = json.dumps(args, ensure_ascii=False)
                    except json.JSONDecodeError:
                        args_str = "{}"
                elif isinstance(arguments_json, (dict, list)):
                    args_str = json.dumps(arguments_json, ensure_ascii=False)
                else:
                    args_str = "{}"

                safe_name = tool_name.replace("\\", "\\\\").replace("'", "\\'")
                safe_args = args_str.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")[:1000]
                safe_result = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                safe_result = safe_result.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")[:500]

                js = f"window.onAddToolCall('{safe_name}', '{safe_args}', '{safe_result}');"
                self.bridge.execute_js(js)
            except Exception as e:
                print(f"{LOG} ❌ 显示工具调用失败: {e}")

    def _on_token_update(self, stats_json: str):
        if self.bridge:
            safe = stats_json.replace("'", "\\'").replace("\\", "\\\\")
            js = f"window.onTokenUpdate('{safe}');"
            try:
                self.bridge.execute_js(js)
            except Exception as e:
                print(f"{LOG} ❌ 推送 token 更新失败: {e}")

    def _on_log_entry(self, entry_json: str):
        if self.bridge:
            safe = entry_json.replace("'", "\\'").replace("\\", "\\\\")
            js = f"window.onLogEntry('{safe}');"
            try:
                self.bridge.execute_js(js)
            except Exception as e:
                print(f"{LOG} ❌ 推送日志条目失败: {e}")

    def push_token_stats(self, total_tokens: int, input_tokens: int, output_tokens: int,
                         context_percent: float, cost: float, max_context: int = 8192):
        stats = {
            "totalTokens": total_tokens,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "contextPercent": round(context_percent, 1),
            "cost": round(cost, 4),
            "maxContext": max_context
        }
        try:
            self.token_update.emit(json.dumps(stats, ensure_ascii=False))
        except Exception as e:
            print(f"{LOG} ❌ token 统计信号发射失败: {e}")

    def push_log_entry(self, model: str, request: str, response: str,
                       input_tokens: int = 0, output_tokens: int = 0,
                       tool_calls: list = None, error: str = None):
        import time
        entry = {
            "timestamp": time.time(),
            "model": model,
            "request": (request or "")[:1000],
            "response": (response or "")[:2000],
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "toolCalls": tool_calls or [],
            "error": error or ""
        }
        try:
            self.log_entry.emit(json.dumps(entry, ensure_ascii=False))
        except Exception as e:
            print(f"{LOG} ❌ 日志条目信号发射失败: {e}")

    def _inject_mcp_context(self):
        try:
            from tools.mcp.host import MCPHost
            tools = MCPHost().get_tools()
            if tools:
                tool_descs = [
                    f"- `{t['function']['name']}`: {t['function']['description']}"
                    for t in tools
                ]
                context = "\n\n## 可用工具\n你可以使用以下 MCP 工具来帮助用户：\n" + "\n".join(tool_descs)
                self.ai_controller.inject_context(context)
        except Exception as e:
            print(f"{LOG} ⚠️ 注入 MCP 上下文失败: {e}")

    def sync_conversations_to_view(self):
        data = self.conversation_model.get_sidebar_data()
        cid = self.conversation_model.current_conversation_id
        title = "新对话"
        for conv in data:
            if conv["id"] == cid:
                title = conv["title"]
                break
        js = (
            f"currentChatId={json.dumps(cid)}; "
            f"document.getElementById('chatTitle').textContent={json.dumps(title, ensure_ascii=False)}; "
            f"renderChatList({json.dumps(data, ensure_ascii=False)});"
        )
        if self.bridge:
            self.bridge.execute_js(js)

    def sync_config_to_view(self):
        if self.bridge:
            self.bridge.execute_js("syncConfig();")