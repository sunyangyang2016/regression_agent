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
    token_update = pyqtSignal(str)
    log_entry = pyqtSignal(str)

    def __init__(self, ai_controller, conversation_model, model_config, parent=None):
        super().__init__(parent)
        self.ai_controller = ai_controller
        self.conversation_model = conversation_model
        self.model_config = model_config
        self.bridge = None
        self._first_reply = True
        # AI 是否正在生成回复（用于并发控制：AI 回复中允许用户输入新消息，
        # 此时先中断旧回复再处理新消息）
        self._is_generating = False
        # 是否有新消息即将发送（中断旧回复后的竞态保护）
        self._pending_new_message = False
        self._token_counter = None
        self._cost_tracker = None
        self._session_total_tokens = 0
        self._session_total_cost = 0.0
        # 3 类 token 分类累计（命中 / 未命中 / 输出）
        self._session_hit_tokens = 0
        self._session_miss_tokens = 0
        self._session_output_tokens = 0
        # 当前 AI 工具调用轮次（由 _on_round 同步更新，用于 tool 消息归档到对应轮次）
        self._current_round_no: Optional[int] = None
        # 发起 AI 调用时的会话 ID（用于回调时校验，防止跨会话写入 →「会话串了」）
        self._active_conversation_id: Optional[str] = None

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
        self.ai_controller.stream_cancelled.connect(self._on_stream_cancelled)
        self.ai_controller.tool_call_received.connect(self._on_tool_call)
        self.ai_controller.raw_log.connect(self._on_raw_log)
        self.ai_controller.progress_usage.connect(self._on_progress_usage)
        self.ai_controller.round_received.connect(self._on_round)
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

        # ====== 并发控制：若 AI 正在回复，先中断旧回复再处理新消息 ======
        if self._is_generating:
            print(f"{LOG} 🔄 AI 正在回复，先中断旧回复再处理新消息")
            self._pending_new_message = True
            self._interrupt_current_generation()

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

        # ====== 发送前：基于真实累计 token 触发滑动/压缩 ======
        # 滑动判断用 API 真实累计（_session_total_tokens），与 UI 百分比一致。
        # 超 90% 时对 ai_controller.messages 执行滑动（保留最新 50% 对话、system 最前），
        # 并同步更新 _session_total_tokens 与 UI 百分比。
        self._apply_context_window_before_send()

        # 记录发起 AI 调用的会话 ID（用于回调时校验，防止跨会话写入 →「会话串了」）
        self._active_conversation_id = self.conversation_model.current_conversation_id

        is_first = not bool(self.conversation_model.current_user_content)
        self.conversation_model.current_user_content = content
        self.conversation_model.save_message("user", content)
        if is_first:
            # ====== 收到第一条用户输入时立即更新会话标题（不等 AI 回复） ======
            self._first_reply = False  # 标题已更新，无需在 _on_stream_complete 中再更新
            try:
                self.conversation_model.update_title(content)
                self.sync_conversations_to_view()
            except Exception as e:
                print(f"{LOG} ⚠️ 更新会话标题失败: {e}")

        self.set_processing.emit(True)
        self.update_message.emit("", "⏳ 思考中…")

        def do_ai_call():
            try:
                # 工具上下文（MCP 状态 + 工具清单）由 AIClient.send_message_async
                # 在每次发送前统一注入（_inject_mcp_server_context /
                # _inject_tool_context_into_system），无需在此重复注入。
                self._is_generating = True
                self.ai_controller.send_message(content)
            except Exception as ex:
                print(f"{LOG} ❌ AI 调用异常: {ex}")
                self._is_generating = False
                self.show_error.emit(str(ex))
                self.complete_message.emit("")

        threading.Thread(target=do_ai_call, daemon=True).start()

    def _apply_context_window_before_send(self):
        """发送消息前基于「当前实际上下文占用」判断并执行滑动

        根因修复：之前用 _session_total_tokens（历史累计口径，随轮次虚高）判断，
        与真实上下文压力脱节，导致 UI 显示 >100% 但滑动不按需触发；
        且滑动后仅按比例缩放累计值，UI 百分比与实际消息占用不符。

        现在：
        1. 用 TokenCounter 估算当前内存消息真实占用（含注入的 system/工具清单）
        2. 超过 max_context × 90% 时 force_slide：保留最新 50% 对话、system 最前
        3. 滑动结果应用回 ai_controller.messages，UI 由 push_token_stats 按真实占用刷新

        注意：push_token_stats 的 totalTokens 保留累计口径（_session_total_tokens），
        contextPercent 由 push_token_stats 内部基于真实消息占用计算。
        """
        try:
            from ai.token_counter import TokenCounter
            max_ctx = self._get_max_context()
            threshold = int(max_ctx * 0.9)
            messages = self.ai_controller.messages or []
            current_usage = TokenCounter.count_messages(messages)
            ctx_pct = (current_usage / max_ctx) * 100 if max_ctx else 0
            # 未超阈值：仅同步一次真实占用到 UI（保持展示与实际一致）
            if current_usage <= threshold:
                self.push_token_stats(
                    self._session_total_tokens,
                    self._session_hit_tokens + self._session_miss_tokens,
                    self._session_output_tokens, ctx_pct,
                    self._session_total_cost, max_ctx,
                    self._session_hit_tokens, self._session_miss_tokens
                )
                return

            from ai.context_window import ContextWindowManager
            mgr = ContextWindowManager(max_context=max_ctx)
            new_messages, stats = mgr.force_slide(messages)
            if not stats.get("triggered") or stats.get("removed_units", 0) <= 0:
                # 无可滑动的对话单元（如全部为 system）——仅同步真实占用
                self.push_token_stats(
                    self._session_total_tokens,
                    self._session_hit_tokens + self._session_miss_tokens,
                    self._session_output_tokens, ctx_pct,
                    self._session_total_cost, max_ctx,
                    self._session_hit_tokens, self._session_miss_tokens
                )
                return
            # 应用滑动结果到 AI 上下文
            self.ai_controller.messages = new_messages
            # 滑动后 UI 按「滑动后的真实占用」刷新（totalTokens 仍用累计口径）
            after_usage = TokenCounter.count_messages(new_messages)
            ctx_pct = (after_usage / max_ctx) * 100 if max_ctx else 0
            self.push_token_stats(
                self._session_total_tokens,
                self._session_hit_tokens + self._session_miss_tokens,
                self._session_output_tokens, ctx_pct,
                self._session_total_cost, max_ctx,
                self._session_hit_tokens, self._session_miss_tokens
            )
            print(f"{LOG} ⚠️ 发送前触发滑动: 上下文 {current_usage} → {after_usage} tokens, "
                  f"移除 {stats['removed_units']} 个旧对话单元, prompt 保留")
        except Exception as e:
            print(f"{LOG} ⚠️ 发送前滑动窗口检查失败: {e}")

    def _interrupt_current_generation(self):
        """中断当前正在进行的 AI 回复（保留已生成的部分内容）"""
        try:
            self.ai_controller.stop_streaming()
        except Exception as e:
            print(f"{LOG} ⚠️ 中断 AI 回复失败: {e}")

    def handle_stop_ai(self):
        """处理用户主动点击「停止」按钮，中断当前 AI 回复"""
        if not self._is_generating:
            return
        print(f"{LOG} ⏹ 用户请求停止 AI 回复")
        self._interrupt_current_generation()

    def handle_compress_context(self):
        """处理用户主动点击「压缩上下文」按钮"""
        if not self.ai_controller.connected:
            self.show_error.emit("AI 客户端未连接，无法压缩上下文")
            return
        try:
            stats = self.ai_controller.compress_context()
            if stats.get("triggered"):
                # 压缩已生效：同步会话累计 token 与 UI 百分比
                after_tokens = stats.get("after_tokens", 0)
                if after_tokens and after_tokens < self._session_total_tokens:
                    self._session_total_tokens = after_tokens
                max_ctx = self._get_max_context()
                ctx_pct = (self._session_total_tokens / max_ctx) * 100
                self.push_token_stats(
                    self._session_total_tokens,
                    self._session_hit_tokens + self._session_miss_tokens,
                    self._session_output_tokens, ctx_pct,
                    self._session_total_cost, max_ctx,
                    self._session_hit_tokens, self._session_miss_tokens
                )
                msg = (f"✅ 上下文已压缩: {stats['before_tokens']} → "
                       f"{stats['after_tokens']} tokens, 压缩 {stats['compressed_units']} 个旧对话单元")
            else:
                msg = f"ℹ️ 暂无需压缩: {stats.get('reason', '当前上下文无需压缩')}"
            print(f"{LOG} {msg}")
            if self.bridge:
                import json as _json
                self.bridge.execute_js(
                    f"window.showToast({_json.dumps(msg, ensure_ascii=False)}, 'info');"
                )
        except Exception as e:
            print(f"{LOG} ⚠️ 压缩上下文失败: {e}")
            self.show_error.emit(f"压缩上下文失败: {e}")

    def _on_stream_cancelled(self, partial_content: str):
        """AI 流被中断：保存已生成的部分内容，恢复 UI"""
        # ====== 会话 ID 校验：若当前会话已切换，丢弃旧会话的回调 ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            print(f"{LOG} ⏹ 忽略跨会话中断回调（发起会话={self._active_conversation_id}, 当前={self.conversation_model.current_conversation_id}）")
            self._active_conversation_id = None
            self._is_generating = False
            self._pending_new_message = False
            return

        print(f"{LOG} ⏹ AI 流已中断（已生成 {len(partial_content or '')} 字符）")
        self._active_conversation_id = None
        # 保存部分内容为 assistant 消息（仅在非空时保存）
        if partial_content and partial_content.strip():
            try:
                self.conversation_model.save_message("assistant", partial_content)
            except Exception as e:
                print(f"{LOG} ⚠️ 保存中断的部分内容失败: {e}")
        # 用户主动点击停止：触发前端「已中断」标记并恢复正常 UI
        if not self._pending_new_message:
            if self.bridge:
                try:
                    self.bridge.execute_js("window.onAIStopped();")
                except Exception as e:
                    print(f"{LOG} ⚠️ 推送中断状态失败: {e}")
            self.complete_message.emit("")
            self.set_processing.emit(False)
        # 新消息接管时不触发 onAIStopped / complete_message（避免清除新气泡引用）
        self._pending_new_message = False
        self._is_generating = False

    def handle_load_conversation(self, conversation_id: str):
        # ====== 切换会话前先中断正在进行的 AI 回复 ======
        # 防止旧会话的流式回调在切换后写入新会话（→「会话串了」）
        if self._is_generating:
            print(f"{LOG} 🔄 切换会话前中断正在进行的 AI 回复")
            self._pending_new_message = False  # 切换会话不是「新消息接管」，无需保留接管标记
            self._interrupt_current_generation()
            # 等待中断完成（AI 任务会在后台很快取消，释放 _is_generating）
            try:
                deadline = time.time() + 2.0
                while self._is_generating and time.time() < deadline:
                    time.sleep(0.02)
            except Exception:
                pass
            self._active_conversation_id = None

        # ====== AI 上下文加载（应用滑动窗口限制：system + 最新 90%） ======
        max_ctx = self._get_max_context()
        messages = self.conversation_model.load_conversation_messages(
            conversation_id, max_context=max_ctx
        )
        self.ai_controller.reset_messages()
        # ====== UI 显示加载（最新 100 条，分页滚动加载更早） ======
        ui_messages = self.conversation_model.load_latest_messages(
            conversation_id, offset=0, limit=100
        )
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
            elif role == "tool":
                # 历史工具调用消息：仅用于 UI 展示，不加载到 AI 上下文。
                # 原因：OpenAI 协议要求 role="tool" 消息必须携带 tool_call_id，
                # 且其对应的 assistant 消息必须携带 tool_calls（配对约束）。
                # 数据库中仅保存了可读的展示文本（如 "🔧 工具调用: ..."），
                # 缺少 tool_call_id / tool_calls / function 名称等协议字段，
                # 直接发送给 API 会触发 400 错误：missing field 'tool_call_id'。
                # 跳过 tool 历史不参与 AI 上下文，不影响 UI 展示（load_latest_messages 渲染）。
                continue

        # 前端显示最新 100 条（不含 system prompt），更早的历史由滚动分页加载
        ui_msgs_json = json.dumps(ui_messages, ensure_ascii=False)
        if self.bridge:
            self.bridge.execute_js(f"loadConversationMessages({ui_msgs_json});")
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

    def load_more_messages(self, conversation_id: str, offset: int):
        """滚动加载更早的历史消息（UI 顶部滚动触发）"""
        try:
            older = self.conversation_model.load_latest_messages(
                conversation_id, offset=offset, limit=50
            )
            if not older:
                if self.bridge:
                    self.bridge.execute_js("window.onNoMoreHistory();")
                return
            if self.bridge:
                self.bridge.execute_js(
                    f"window.prependHistoryMessages({json.dumps(older, ensure_ascii=False)});"
                )
        except Exception as e:
            print(f"{LOG} ⚠️ 滚动加载历史消息失败: {e}")

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
        # ====== 会话 ID 校验：若当前会话已切换，丢弃旧会话的回复（→ 防「会话串了」） ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            print(f"{LOG} ❌ 忽略跨会话回复回调（发起会话={self._active_conversation_id}, 当前={self.conversation_model.current_conversation_id}），丢弃旧回复")
            self._active_conversation_id = None
            self._is_generating = False
            self._pending_new_message = False
            self.set_processing.emit(False)
            return

        self._active_conversation_id = None
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

        # 使用提取的真实内容保存和显示（token_count = input+output，代表该轮 context 增量）
        try:
            self.conversation_model.save_message(
                "assistant", content,
                token_count=input_tokens + output_tokens
            )
            self.update_message.emit("", content)
            self.complete_message.emit("")
            self.set_processing.emit(False)
            self._is_generating = False
        except Exception as e:
            print(f"{LOG} ⚠️ 保存/显示助手回复失败: {e}")
            self._is_generating = False

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
        # context 占用用本轮 API 真实 prompt_tokens（= 当前实际发送给模型的消息 token），
        # 与累计 token 一起刷新，避免进度条与 token 显示脱节或虚高超 100%
        ctx_pct = (input_tokens / max_ctx) * 100 if max_ctx and input_tokens > 0 else 0

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

    def _on_round(self, round_json: str):
        """接收 AI 每一轮的回复数据并写入消息表

        ⚠️ 只保存「工具调用中间轮」（marker = tool_call）。
        最终回复（marker = final）由 _on_stream_complete 统一保存（含 token_count），
        避免同一回复在 round 和 complete 两个事件中被重复写入数据库 → UI 显示两次。
        """
        # ====== 会话 ID 校验：若当前会话已切换，忽略旧会话的 round 数据 ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            return
        try:
            data = json.loads(round_json)
            round_no = int(data.get("round", 1))
            marker = data.get("marker", "final")
            text = data.get("text", "")
            # 同步当前工具调用轮次（供 _on_tool_call 归档 tool 消息使用）——先执行，
            # 后续 return 分支也必须已更新轮次，保证工具消息归档正确
            self._current_round_no = round_no
            # final 轮不在此保存（_on_stream_complete 统一保存），避免重复
            if marker == "final":
                return
            # 工具调用前的中间轮若无文本内容则不写历史（多轮工具调用的第一轮模型
            # 只发 tool_calls 没有输出文本，无条件保存会产生空 assistant 记录 → 会话
            # 加载时显示空白 AI 气泡，视觉上像「问了两次」）
            if not text or not text.strip():
                return
            # 仅保存工具调用中间轮（多轮工具调用过程记录）
            self.conversation_model.save_message("assistant", text, round_no=round_no, marker=marker)
            print(f"{LOG} 💾 AI 第 {round_no} 轮工具调用回复已写入消息表（标记: {marker}）")
        except Exception as e:
            print(f"{LOG} ⚠️ 保存 AI 轮次数据失败: {e}")

    def _on_stream_error(self, error_msg: str):
        # ====== 会话 ID 校验：若当前会话已切换，忽略旧会话的错误回调 ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            print(f"{LOG} ⚠️ 忽略跨会话错误回调（发起会话={self._active_conversation_id}, 当前={self.conversation_model.current_conversation_id}）")
            self._active_conversation_id = None
            self._is_generating = False
            self._pending_new_message = False
            return
        self._active_conversation_id = None
        self.update_message.emit("", f"❌ {error_msg}")
        self.complete_message.emit("")
        self.set_processing.emit(False)
        self._is_generating = False

    def _on_tool_call(self, tool_name: str, arguments_json: str, result: str):
        # ====== 会话 ID 校验：已切换会话时丢弃旧会话的工具调用归档，防止「会话串了」 ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            print(f"{LOG} ⏹ 忽略跨会话工具调用归档（发起会话={self._active_conversation_id}, 当前={self.conversation_model.current_conversation_id}）")
            self._active_conversation_id = None
            return

        # ====== 组装可读的工具调用文本（完整保留工具名/参数/结果，不截断） ======
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

            result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else (result or "")
            tool_content = f"🔧 工具调用: {tool_name}\n参数: {args_str}\n结果: {result_str}"
        except Exception as e:
            print(f"{LOG} ⚠️ 解析工具调用参数失败: {e}")
            tool_content = f"🔧 工具调用: {tool_name}\n结果: {result or ''}"

        # ====== 工具调用归档到历史（数据库持久化） ======
        # 目的：工具调用信息「放入历史」，会话切换后仍可查看完整调用记录。
        try:
            self.conversation_model.save_message(
                "tool", tool_content,
                round_no=self._current_round_no,
            )
            print(f"{LOG} 💾 工具调用已归档到历史: {tool_name} (round={self._current_round_no})")
        except Exception as e:
            print(f"{LOG} ⚠️ 保存工具调用到历史失败: {e}")

        # ====== 前端 tool 消息展示 ======
        # 以 tool 消息样式显示（🔧 工具 + monospace 内容），并插入到 AI 回答之前，
        # 与历史加载样式统一，不再使用 onAddToolCall 的「工具调用」卡片样式。
        if self.bridge:
            try:
                self.bridge.execute_js(
                    f"window.chatApp.insertToolMessage({json.dumps(tool_content, ensure_ascii=False)});"
                )
            except Exception as e:
                print(f"{LOG} ❌ 显示工具调用失败: {e}")

    def _on_progress_usage(self, usage_json: str):
        """多轮工具调用中间进度 token：立即刷新 UI 面板（不重复入库，最终 complete 精确结算）"""
        # ====== 会话 ID 校验：若当前会话已切换，忽略旧会话的中间 token 统计 ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            return

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
            # context 占用用 API 本轮真实 prompt_tokens（与 token 累计同一次推送刷新）
            prompt_tokens = int(data.get("prompt_tokens", 0))
            ctx_pct = (prompt_tokens / max_ctx) * 100 if max_ctx and prompt_tokens > 0 else 0
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
        # ====== 会话 ID 校验：若当前会话已切换，忽略旧会话的原始日志（防止日志串扰） ======
        if self._active_conversation_id is not None and \
           self._active_conversation_id != self.conversation_model.current_conversation_id:
            return

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
        """推送 token 统计到 UI

        - totalTokens：保留传入的「累计口径」值（会话累计 token，随轮次增长）
          由调用方传入 _session_total_tokens，前端 tokenCount 显示累计。
        - contextPercent：用「当前发送给模型的实际消息占用」计算，
          避免用历史累计口径使进度条虚高超 100%。
        - hit/miss/output 与 cost 继续使用累计统计口径。
        """
        # 尊重调用方传入的 context_percent（各调用点已用 API 真实 prompt_tokens 计算），
        # 使 context 占用与 token 显示在同一次推送中一起刷新。
        ctx_pct = float(context_percent)
        # 进度条百分比钳制到 0~100，避免虚高超界
        ctx_pct = max(0.0, min(ctx_pct, 100.0))
        stats = {
            "totalTokens": total_tokens,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "hitTokens": hit_tokens,
            "missTokens": miss_tokens,
            "contextPercent": round(ctx_pct, 1),
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