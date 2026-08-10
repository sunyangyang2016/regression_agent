"""
ChatBridge - 聊天对话桥接
处理对话消息、会话管理、流式更新等前后端交互
"""
import json
import re
from PyQt5.QtCore import pyqtSlot, pyqtSignal

from .base import BridgeBase


class ChatBridge(BridgeBase):
    """聊天对话桥接 — 对话/会话操作

    职责：纯通用消息通道。
    MCP 安装等专用逻辑通过 set_content_sink 可选钩子接入
    （默认 None，正常会话零影响）。
    """

    def __init__(self, app_controller):
        super().__init__(app_controller)
        # 可选回调钩子（MCP 安装捕获 AI 回复用；默认 None）
        self._on_content_chunk = None   # 收到 AI 流式片段时回调(chunk)
        self._on_stream_done = None     # AI 流式完成时回调()
        # 语音交互模式：缓存最近一次 AI 流式回复（供 TTS 朗读）
        self._last_ai_reply = ""
        # 流式朗读：断句累积缓冲（AI 边输出边播放）
        self._tts_buffer = ""
        # 已送入 TTS 的字符数（AIController 推送的是累积全文，
        # 用此记录提取增量，避免已播内容重复累积 / 重复播放）
        self._tts_last_len = 0

    def set_content_sink(self, chunk_cb, done_cb):
        """注册内容回调（MCP 安装启动时由调用方注册；结束后 clear）"""
        self._on_content_chunk = chunk_cb
        self._on_stream_done = done_cb

    def clear_content_sink(self):
        """清除内容回调（安装结束/超时后调用）"""
        self._on_content_chunk = None
        self._on_stream_done = None

    # ==========================================
    # 前端 → 后端（通过 @pyqtSlot 暴露给 JS）
    # ==========================================

    @pyqtSlot(str)
    def sendToAI(self, content):
        """接收前端消息，转发到 ChatController"""
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            self.app_controller.chat_controller.handle_user_message(content)

    @pyqtSlot()
    def stopAI(self):
        """中断当前 AI 回复（用户点击停止按钮）"""
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            self.app_controller.chat_controller.handle_stop_ai()

    @pyqtSlot()
    def compressContext(self):
        """压缩当前会话上下文（用户点击压缩按钮主动触发）"""
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            self.app_controller.chat_controller.handle_compress_context()

    @pyqtSlot(str, int)
    def loadMoreMessages(self, conversation_id, offset):
        """分页加载更早的历史消息（UI 滚动到顶部时触发）"""
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            self.app_controller.chat_controller.load_more_messages(conversation_id, offset)

    @pyqtSlot(str)
    def loadConversation(self, conversation_id):
        """加载历史会话"""
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            self.app_controller.chat_controller.handle_load_conversation(conversation_id)

    @pyqtSlot(str, str)
    def addMessage(self, content, role):
        pass

    @pyqtSlot(float)
    def setZoomFactor(self, ratio):
        try:
            if self.app_controller and self.app_controller.webview:
                self.app_controller.webview.setZoomFactor(ratio)
        except Exception as e:
            print(f"[Bridge] ❌ setZoomFactor 失败: {e}")

    def _reset_chat_state(self, chat_controller=None):
        """重置会话状态（新建对话/删除对话后调用），确保各会话完全隔离

        关键点：
        - 必须重置 AIController.messages（否则旧会话历史串入新会话 →「会话串了」）
        - 必须重置 AI 通信日志缓存 / 日志文件路径（否则新会话展示旧日志）
        - 必须重置 token / 费用分类统计（否则新会话携带旧会话的累计数据）
        - 必须重置标题更新标志 _first_reply（否则新会话无法生成标题）
        """
        cc = chat_controller or self.app_controller.chat_controller
        if not cc:
            return

        # 0. 若 AI 正在回复，先中断旧回复（防止旧会话回调写入新会话）
        #    中断会在后台取消 AI 任务并同步触发 stream_cancelled 回调，
        #    该回调会正确保存部分内容到旧会话并清除 _active_conversation_id。
        if getattr(cc, '_is_generating', False):
            try:
                print("[Bridge] 重置会话状态：中断正在进行的 AI 回复")
                cc._pending_new_message = False
                cc._interrupt_current_generation()
            except Exception as e:
                print(f"[Bridge] ⚠️ 中断 AI 回复失败: {e}")
        # 清除活动会话 ID（后续任何延迟回调都会被丢弃）
        cc._active_conversation_id = None

        # 1. 重置 AI 消息历史（最关键：防止旧会话上下文串入新会话）
        ai_controller = getattr(cc, 'ai_controller', None)
        if ai_controller and hasattr(ai_controller, 'reset_messages'):
            ai_controller.reset_messages()

        conv_model = getattr(cc, 'conversation_model', None)
        if conv_model is not None:
            # 2. 重置当前会话 ID 和用户内容（下次发送时创建全新会话）
            conv_model._current_conversation_id = None
            conv_model._current_user_content = None

        # 3. 重置 AI 通信日志（防止旧会话日志串入新会话）
        cc._session_logs = []
        cc._log_file_path = None

        # 4. 重置 token / 费用分类统计（防止新会话携带旧会话累计数据）
        cc._session_total_tokens = 0
        cc._session_total_cost = 0.0
        cc._session_hit_tokens = 0
        cc._session_miss_tokens = 0
        cc._session_output_tokens = 0

        # 5. 重置标题更新标志（新会话首条回复生成新标题）
        cc._first_reply = True

        # 5.1 重置当前工具调用轮次（防止旧会话的轮次标记串入新会话）
        cc._current_round_no = None

        # 6. 推送归零的 token 统计到 UI
        try:
            cc.push_token_stats(0, 0, 0, 0.0, 0.0)
        except Exception as e:
            print(f"[Bridge] 重置 token 统计推送失败: {e}")

    @pyqtSlot()
    def newConversation(self):
        """创建新对话（重置状态，不写数据库，不发消息不生成条目）"""
        try:
            self._reset_chat_state()
            print(f"[Bridge] newConversation 重置状态成功")
        except Exception as e:
            import traceback
            print(f"[Bridge] newConversation 失败: {e}")
            traceback.print_exc()

    @pyqtSlot(str)
    def deleteConversation(self, conversation_id):
        """删除会话"""
        print(f"[Bridge] deleteConversation: {conversation_id}")
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            try:
                self.app_controller.chat_controller.conversation_model.delete_conversation(conversation_id)
                print(f"[Bridge] 已删除会话: {conversation_id}")
            except Exception as e:
                print(f"[Bridge] deleteConversation 失败: {e}")

    @pyqtSlot(str)
    def deleteConversationAndNew(self, conversation_id):
        """删除会话，重置为新对话（不创建新条目）"""
        print(f"[Bridge] deleteConversationAndNew: {conversation_id}")
        if not (self.app_controller and hasattr(self.app_controller, 'chat_controller')):
            return
        try:
            import json
            chat_controller = self.app_controller.chat_controller
            conv_model = chat_controller.conversation_model
            conv_model.delete_conversation(conversation_id)
            # 统一重置会话状态（AI 消息 / token / 日志等全部重置，确保会话隔离）
            self._reset_chat_state(chat_controller)
            data = conv_model.get_sidebar_data()
            js = (
                f"if (typeof updateChatTabTitle === 'function') updateChatTabTitle('新对话');"
                "document.getElementById('chatMessages').innerHTML = "
                "'<div class=\"welcome-screen\" id=\"welcomeScreen\">' + "
                "'<div class=\"welcome-icon\">🤖</div>' + "
                "'<h1 class=\"welcome-title\">AI 智能助手</h1>' + "
                "'<div class=\"quick-actions\">' + "
                "'<div class=\"quick-action\" onclick=\"quickAction(\\'写一个 Python 函数\\')\"><i class=\"fas fa-code\"></i><span class=\"label\">写代码</span></div>' + "
                "'<div class=\"quick-action\" onclick=\"quickAction(\\'帮我解释这个概念\\')\"><i class=\"fas fa-lightbulb\"></i><span class=\"label\">解释概念</span></div>' + "
                "'<div class=\"quick-action\" onclick=\"quickAction(\\'分析这段数据\\')\"><i class=\"fas fa-chart-bar\"></i><span class=\"label\">分析数据</span></div>' + "
                "'<div class=\"quick-action\" onclick=\"quickAction(\\'翻译成中文\\')\"><i class=\"fas fa-language\"></i><span class=\"label\">翻译</span></div>' + "
                "'</div></div>';"
                "window.chatApp.messages=[];"
                f"renderChatList({json.dumps(data, ensure_ascii=False)});"
            )
            self.execute_js(js)
            print(f"[Bridge] 已删除并切到新对话, 剩余{len(data)}条")
        except Exception as e:
            import traceback
            print(f"[Bridge] deleteConversationAndNew 失败: {e}")
            traceback.print_exc()

    @pyqtSlot(result=str)
    def getConversations(self):
        """获取对话列表（用于侧边栏导航）"""
        print("[Bridge] getConversations 被调用")
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            try:
                cc = self.app_controller.chat_controller
                print(f"[Bridge] chat_controller OK, conversation_model={cc.conversation_model}")
                data = cc.conversation_model.get_sidebar_data()
                print(f"[Bridge] get_sidebar_data 返回 {len(data)} 条")
                import json
                result = json.dumps(data, ensure_ascii=False)
                print(f"[Bridge] JSON 前100字符: {result[:100]}")
                return result
            except Exception as e:
                import traceback
                print(f"[Bridge] getConversations 失败: {e}")
                traceback.print_exc()
        else:
            print(f"[Bridge] app_controller={self.app_controller}, has chat_controller={hasattr(self.app_controller, 'chat_controller') if self.app_controller else 'N/A'}")
        return "[]"

    # ==========================================
    # 后端 → 前端（Controller 调用 → execute_js）
    # ==========================================

    def on_stream_update(self, content: str):
        """流式更新消息内容（基础转发；MCP 等注册的 chunk 回调会额外收到分片）

        注意：AIController 推送的 content 是「累积全文」（非增量），
        UI 侧 onStreamUpdate 依赖全文全量渲染；而 TTS 只需增量，
        这里用 _tts_last_len 提取「新增部分」再喂给 _feed_tts_stream，
        避免已播过的内容被反复累积 → 重复播放。
        """
        c = json.dumps(content)
        self.execute_js(f"window.onStreamUpdate({c});")
        # 缓存 AI 回复内容（跳过"思考中…"占位），供语音交互模式 TTS 朗读使用
        if content and content != '⏳ 思考中…':
            self._last_ai_reply = content
            # 只把「新增部分」送入流式朗读（累积全文 → 增量提取）
            if len(content) > self._tts_last_len:
                delta = content[self._tts_last_len:]
                self._tts_last_len = len(content)
                self._feed_tts_stream(delta)
        if self._on_content_chunk is not None:
            try:
                self._on_content_chunk(content)
            except Exception as e:
                print(f"[ChatBridge] ⚠️ chunk 回调失败: {e}")

    def _feed_tts_stream(self, delta: str):
        """累积流式内容，遇断句标点立即触发语音朗读（AI 边输出边播）"""
        if not delta:
            return
        self._tts_buffer += delta
        # 按断句符（。？！；换行）切出完整句子
        sentences = re.split(r'(?<=[。？！；\n])', self._tts_buffer)
        if len(sentences) > 1:
            complete = ''.join(sentences[:-1]).strip()
            if complete:
                self._speak_sentence(complete)
            self._tts_buffer = sentences[-1]

    def _speak_sentence(self, sentence: str):
        """调用 VoiceBridge 朗读单个完整句子（语音交互模式下才播放）"""
        vb = getattr(self.app_controller, 'voice_bridge', None)
        if vb and getattr(vb, '_voice_chat_active', False):
            try:
                vb.speak_stream(sentence)
            except Exception as e:
                print(f"[ChatBridge] ⚠️ 流式朗读失败: {e}")

    def _flush_tts_stream(self):
        """AI 回复完成：刷新缓冲中剩余的未播放内容（如无标点结尾的片段）"""
        if not self._tts_buffer.strip():
            self._tts_buffer = ""
            return
        vb = getattr(self.app_controller, 'voice_bridge', None)
        if vb and getattr(vb, '_voice_chat_active', False):
            try:
                vb.speak_stream(self._tts_buffer.strip())
            except Exception as e:
                print(f"[ChatBridge] ⚠️ 流式朗读刷新失败: {e}")
        self._tts_buffer = ""

    def on_stream_complete(self):
        """流式响应完成（基础转发；MCP 注册的完成回调会在此触发且仅触发一次）"""
        self.execute_js("window.onStreamComplete();")
        if self._on_stream_done is not None:
            try:
                cb, self._on_stream_done = self._on_stream_done, None
                cb()
            except Exception as e:
                print(f"[ChatBridge] ⚠️ done 回调失败: {e}")
                self._on_stream_done = None
        # 语音交互模式：AI 回复完成 → 先刷新流式朗读缓冲（播放剩余内容），
        # 再通知 VoiceBridge 标记回复完成；最后一句播完自动重新聆听。
        try:
            vb = getattr(self.app_controller, 'voice_bridge', None)
            if vb:
                self._flush_tts_stream()
                reply_text = self._last_ai_reply   # 取缓存的真实 AI 回复
                self._last_ai_reply = ""           # 用完清空
                vb.on_ai_reply_complete(reply_text)
        except Exception as e:
            print(f"[ChatBridge] ⚠️ 语音交互联动失败: {e}")
        finally:
            # 本轮结束：重置增量游标，下一轮回复从头累积
            self._tts_last_len = 0

    def on_set_processing(self, processing: bool):
        """设置处理状态"""
        self.execute_js(f"window.onSetProcessing({str(processing).lower()});")

    def on_show_error(self, error_msg: str):
        """显示错误消息"""
        e = json.dumps(error_msg)
        self.execute_js(f"window.onShowError({e});")
