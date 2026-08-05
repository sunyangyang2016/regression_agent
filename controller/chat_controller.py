"""
ChatController - 聊天控制器
接收用户交互事件，调用 Model 更新数据，决定 View 如何刷新
"""
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Optional
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
        # 3 类 token 分类累计（命中 / 未命中 / 输出）
        self._session_hit_tokens = 0
        self._session_miss_tokens = 0
        self._session_output_tokens = 0

        # ====== AI 通信日志持久化 ======
        # 当前会话累积的底层原始日志明细（内存缓存，落盘时写入 JSON 文件）
        self._session_logs: list = []
        # 当前会话的日志文件绝对路径（首次落盘时确定，之后各轮追加写同一文件）
        self._log_file_path: Optional[str] = None
        # 日志保存锁（避免多线程并发写文件）
        self._log_lock = threading.Lock()

        self.ai_controller.stream_chunk.connect(self._on_stream_chunk)
        self.ai_controller.stream_complete.connect(self._on_stream_complete)
        self.ai_controller.stream_error.connect(self._on_stream_error)
        self.ai_controller.tool_call_received.connect(self._on_tool_call)
        self.ai_controller.raw_log.connect(self._on_raw_log)
        self.ai_controller.progress_usage.connect(self._on_progress_usage)
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

        # ====== 入站内容过滤（安全插件 hook 广播） ======
        try:
            from plugins.hook_registry import HookRegistry
            results = HookRegistry().trigger("message:before_send", json.dumps(
                {"text": content}, ensure_ascii=False))
            for r in HookRegistry.parse_results(results):
                if r.get("blocked"):
                    self.show_error.emit(r.get("message", "内容已被安全策略阻止"))
                    self.complete_message.emit("")
                    return
                masked = r.get("masked_text")
                if masked is not None:
                    content = masked
        except Exception as e:
            print(f"{LOG} ⚠️ 入站内容过滤失败: {e}")

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
        # 从数据库加载已保存的 token 数据（分类统计）
        token_stats = self.conversation_model.get_token_stats(conversation_id)
        self._session_total_tokens = token_stats["total"]
        self._session_hit_tokens = token_stats["hit"]
        self._session_miss_tokens = token_stats["miss"]
        self._session_output_tokens = token_stats["output"]
        # 累计费用由 3 类累计 token 按模型单价推导，确保 UI 上费用与 token 同步显示
        self._session_total_cost = self._calculate_session_cost(
            self._session_hit_tokens, self._session_miss_tokens, self._session_output_tokens
        )
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
            # 恢复会话的 token 统计显示（命中/未命中/输出 分类完整恢复）
            max_ctx = self._get_max_context()
            ctx_pct = (self._session_total_tokens / max_ctx) * 100
            self.push_token_stats(
                self._session_total_tokens,
                self._session_hit_tokens + self._session_miss_tokens,
                self._session_output_tokens, ctx_pct,
                self._session_total_cost, max_ctx,
                self._session_hit_tokens, self._session_miss_tokens
            )

        # ====== 加载该会话的历史 AI 通信日志 ======
        self._load_session_logs_from_db(conversation_id)

    # ==========================================
    # AI 通信日志持久化
    # ==========================================

    def _load_session_logs_from_db(self, conversation_id: str):
        """从数据库读取会话的日志文件路径，加载历史日志到前端"""
        log_file = self.conversation_model.get_log_file(conversation_id)
        logs = []
        if log_file and os.path.exists(log_file):
            logs = self._read_log_file(log_file)
        self._log_file_path = log_file if (log_file and os.path.exists(log_file)) else None
        self._session_logs = list(logs)

        if self.bridge:
            try:
                self.bridge.execute_js(
                    f"window.loadConversationLogs({json.dumps(json.dumps(logs, ensure_ascii=False), ensure_ascii=False)});"
                )
            except Exception as e:
                print(f"{LOG} ❌ 推送历史日志失败: {e}")

    def _read_log_file(self, log_file: str) -> list:
        """读取日志 JSON 文件，返回 logs 数组（异常返回空列表）"""
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("logs", []) if isinstance(data, dict) else []
        except Exception as e:
            print(f"{LOG} ⚠️ 读取日志文件失败: {e}")
            return []

    def _save_session_logs(self):
        """将当前会话累积的日志写入日志文件（幂等：首轮创建文件，后续轮追加内容）

        文件名规则：{会话标题}_{时间戳}.json，保存到项目 logs/history/ 目录。
        会话标题在首条回复完成后已确定，因此首轮落盘时使用当时的标题。
        """
        if not self._session_logs:
            return

        with self._log_lock:
            try:
                cid = self.conversation_model.current_conversation_id
                if not cid:
                    return

                # 首次落盘：确定日志文件路径（之后沿用同一文件）
                if not self._log_file_path:
                    self._log_file_path = self._make_log_file_path()

                # 读取现有文件（若存在）保留原始创建时间元数据
                existing = {}
                if os.path.exists(self._log_file_path):
                    try:
                        with open(self._log_file_path, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                    except Exception:
                        existing = {}
                    logs = existing.get("logs", []) if isinstance(existing, dict) else []
                else:
                    logs = []

                # 合并本次新增日志（按内容去重防重复追加）
                existing_ts = {json.dumps(l, ensure_ascii=False, sort_keys=True) for l in logs}
                for entry in self._session_logs:
                    key = json.dumps(entry, ensure_ascii=False, sort_keys=True)
                    if key not in existing_ts:
                        logs.append(entry)
                        existing_ts.add(key)

                title = self._get_conversation_title(cid)
                data = {
                    "session_id": cid,
                    "title": title,
                    "model": self.model_config.get("api", "model") or "deepseek-chat",
                    "updated_at": datetime.now().isoformat(),
                    "logs": logs,
                }
                if isinstance(existing, dict) and existing.get("created_at"):
                    data["created_at"] = existing.get("created_at")
                else:
                    data["created_at"] = datetime.now().isoformat()

                # 写入文件
                with open(self._log_file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)

                # 将日志文件路径保存到数据库
                self.conversation_model.update_log_file(self._log_file_path)
                print(f"{LOG} 💾 会话日志已保存: {self._log_file_path} ({len(logs)} 条)")

            except Exception as e:
                print(f"{LOG} ❌ 保存会话日志失败: {e}")

    def _make_log_file_path(self) -> str:
        """生成日志文件路径：logs/history/{标题}_{时间戳}.json"""
        from core.path_manager import get_path_manager
        pm = get_path_manager()
        history_dir = pm.ensure_dir("logs", "history")

        title = self._get_conversation_title(self.conversation_model.current_conversation_id) or "新对话"
        safe_title = self._sanitize_filename(title)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{ts}.json"
        return str(history_dir / filename)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符（Windows/Linux 通用）"""
        name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name)
        name = name.strip(" .")
        name = name[:50]
        return name or "对话"

    def _get_conversation_title(self, cid: str) -> str:
        """从会话仓库中获取标题"""
        try:
            if hasattr(self.conversation_model, "_conv_repo") and self.conversation_model._conv_repo:
                conv = self.conversation_model._conv_repo.get(cid)
                if conv and conv.title:
                    return conv.title
            return "新对话"
        except Exception:
            return "新对话"

    def _get_max_context(self) -> int:
        """获取当前激活模型配置的最大上下文 token 数（默认 65536，即 64K）"""
        try:
            val = self.model_config.get("api", "max_context")
            return int(val) if val else 65536
        except Exception:
            return 65536

    def _calculate_session_cost(self, hit_tokens: int, miss_tokens: int, output_tokens: int) -> float:
        """按当前激活模型的配置单价计算累计费用（每百万 token 计费）

        费用 = 命中token/1M × 命中单价 + 未命中token/1M × 未命中单价 + 输出token/1M × 输出单价
        """
        from ai.cost_tracker import get_model_pricing, calculate_cost
        pricing = get_model_pricing(self.model_config)
        return round(calculate_cost(hit_tokens, miss_tokens, output_tokens, pricing), 4)

    def _on_stream_chunk(self, content: str):
        self.update_message.emit("", content)

    def _on_stream_complete(self, full_response: str):
        # 尝试从流式响应中提取 OpenAI SDK 返回的精确 token 数和真实内容
        user_content = self.conversation_model.current_user_content or ""
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        content = full_response

        if full_response.startswith('{"content"'):
            try:
                parsed = json.loads(full_response)
                usage = parsed.get("_usage", {})
                if usage:
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                    cached_tokens = usage.get("cached_tokens", 0) or 0
                content = parsed.get("content", full_response)
            except Exception:
                pass

        # ====== 出站内容过滤（安全插件 hook 广播） ======
        try:
            from plugins.hook_registry import HookRegistry
            results = HookRegistry().trigger("message:before_complete", json.dumps(
                {"content": content}, ensure_ascii=False))
            for r in HookRegistry.parse_results(results):
                masked = r.get("masked_text")
                if masked is not None:
                    content = masked
                if r.get("blocked"):
                    # 出站严重违规：替换为安全提示
                    content = r.get("message", "内容已被安全策略过滤")
        except Exception as e:
            print(f"{LOG} ⚠️ 出站内容过滤失败: {e}")

        # 使用提取的真实内容保存和显示
        try:
            self.conversation_model.save_message("assistant", content)
            self.update_message.emit("", content)
            self.complete_message.emit("")
            self.set_processing.emit(False)
        except Exception as e:
            print(f"{LOG} ⚠️ 保存/显示助手回复失败: {e}")

        # ====== 发布 AI 回复事件（供插件订阅，如监控插件按 {{标记}} 提取结论/告警） ======
        try:
            from core.plugin_bus import PluginBus
            PluginBus.publish(
                "ai_reply",
                content,
                self.conversation_model.current_conversation_id or "",
            )
        except Exception as e:
            print(f"{LOG} ⚠️ 发布 ai_reply 事件失败: {e}")

        try:
            if input_tokens == 0 and output_tokens == 0:
                from ai.token_counter import TokenCounter
                input_tokens = TokenCounter.count_text(user_content)
                output_tokens = TokenCounter.count_text(content)
        except Exception as e:
            print(f"{LOG} ⚠️ token 文本计数失败，使用近似值: {e}")
            input_tokens = max(len(user_content) // 4, 1)
            output_tokens = max(len(content) // 4, 1)

        # 命中 / 未命中 / 输出 3 类 token 拆分
        # 命中 token = cached_tokens（缓存命中输入）
        # 未命中 token = prompt_tokens - cached_tokens（未命中缓存的输入）
        # 输出 token = completion_tokens
        hit_tokens = min(cached_tokens, input_tokens) if input_tokens > 0 else 0
        miss_tokens = max(input_tokens - hit_tokens, 0)

        self._session_hit_tokens += hit_tokens
        self._session_miss_tokens += miss_tokens
        self._session_output_tokens += output_tokens
        self._session_total_tokens += input_tokens + output_tokens

        max_ctx = self._get_max_context()
        ctx_pct = (self._session_total_tokens / max_ctx) * 100

        # 累计费用由 3 类累计 token 按当前模型的配置单价推导，确保 UI 上费用与 token 同步刷新
        self._session_total_cost = self._calculate_session_cost(
            self._session_hit_tokens, self._session_miss_tokens, self._session_output_tokens
        )

        # 保存 3 类 token 分类统计到数据库（独立保护，异常不阻断 UI 推送）
        try:
            self.conversation_model.update_token_stats(
                self._session_hit_tokens, self._session_miss_tokens, self._session_output_tokens
            )
        except Exception as e:
            print(f"{LOG} ⚠️ token 统计入库失败: {e}")

        # push_token_stats 必须最终执行，保证 UI token 面板更新（MCP 安装等场景）
        try:
            self.push_token_stats(
                self._session_total_tokens,
                self._session_hit_tokens + self._session_miss_tokens,
                self._session_output_tokens, ctx_pct,
                self._session_total_cost, max_ctx, self._session_hit_tokens, self._session_miss_tokens
            )
        except Exception as e:
            print(f"{LOG} ⚠️ token 统计推送失败: {e}")
            import traceback
            traceback.print_exc()
        # 说明：不再推送概要日志（push_log_entry），
        # 因为底层原始 JSON 日志（raw 类型）已完整包含请求/响应载荷与 token 统计，
        # 避免日志对话框中「响应显示完成后又重复显示一条对话信息」。
        # push_log_entry 方法保留，供其他场景需要时调用。

        # 首条回复完成后更新标题（独立保护：异常不影响后续流程）
        if self._first_reply:
            self._first_reply = False
            try:
                title_content = self.conversation_model.current_user_content
                if title_content:
                    self.conversation_model.update_title(title_content)
                    self.sync_conversations_to_view()
            except Exception as e:
                print(f"{LOG} ⚠️ 更新会话标题失败: {e}")

        # ====== 将本轮的 AI 通信日志写入日志文件 ======
        self._save_session_logs()

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

    def _on_progress_usage(self, usage_json: str):
        """多轮工具调用中间进度 token：立即刷新 UI 面板（不重复入库，最终 complete 精确结算）"""
        try:
            data = json.loads(usage_json)
            accum_input = int(data.get("accum_input", 0))
            accum_output = int(data.get("accum_output", 0))
            accum_hit = int(data.get("accum_hit", 0))
            accum_miss = int(data.get("accum_miss", 0))
            self._session_total_tokens = accum_input + accum_output
            self._session_output_tokens = accum_output
            # 补全：中间轮同样更新命中/未命中累计（与 accum_input 直接赋值方式一致，
            # stream_handler 端已做跨轮累计；最终 complete 仍以精确 usage 覆盖结算）
            self._session_hit_tokens = accum_hit
            self._session_miss_tokens = accum_miss
            max_ctx = self._get_max_context()
            ctx_pct = (self._session_total_tokens / max_ctx) * 100
            self._session_total_cost = self._calculate_session_cost(
                self._session_hit_tokens, self._session_miss_tokens, self._session_output_tokens
            )
            self.push_token_stats(
                self._session_total_tokens,
                self._session_hit_tokens + self._session_miss_tokens,
                self._session_output_tokens, ctx_pct,
                self._session_total_cost, max_ctx, self._session_hit_tokens, self._session_miss_tokens
            )
        except Exception as e:
            print(f"{LOG} ⚠️ 中间 token 推送失败: {e}")

    def _on_raw_log(self, raw_json: str):
        """接收底层 AI 通信原始 JSON 日志，转发到前端日志对话框"""
        # 缓存到当前会话（落到日志文件）
        try:
            entry = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            self._session_logs.append(entry)
        except Exception:
            pass

        if self.bridge:
            try:
                # 通过 onLogEntry 统一推送到前端（前端会识别 type: "raw" 渲染）
                self._on_log_entry(raw_json)
            except Exception as e:
                print(f"{LOG} ❌ 推送底层原始日志失败: {e}")

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
            # 用 json.dumps 生成 JS 安全的字符串字面量，避免特殊字符（引号/反斜杠/换行等）破坏 JS 语法
            try:
                js = f"window.onLogEntry({json.dumps(entry_json, ensure_ascii=False)});"
                self.bridge.execute_js(js)
            except Exception as e:
                print(f"{LOG} ❌ 推送日志条目失败: {e}")

    def push_token_stats(self, total_tokens: int, input_tokens: int, output_tokens: int,
                         context_percent: float, cost: float, max_context: int = 65536,
                         hit_tokens: int = 0, miss_tokens: int = 0):
        stats = {
            "totalTokens": total_tokens,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "hitTokens": hit_tokens,
            "missTokens": miss_tokens,
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