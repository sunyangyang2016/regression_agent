"""
ChatBridge - 聊天对话桥接
处理对话消息、会话管理、流式更新等前后端交互
"""
import json
from PyQt5.QtCore import pyqtSlot, pyqtSignal

from .base import BridgeBase


class ChatBridge(BridgeBase):
    """聊天对话桥接 — 对话/会话操作"""

    # ==========================================
    # 前端 → 后端（通过 @pyqtSlot 暴露给 JS）
    # ==========================================

    @pyqtSlot(str)
    def sendToAI(self, content):
        """接收前端消息，转发到 ChatController"""
        if self.app_controller and hasattr(self.app_controller, 'chat_controller'):
            self.app_controller.chat_controller.handle_user_message(content)

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

    @pyqtSlot()
    def newConversation(self):
        """创建新对话（重置状态，不写数据库，不发消息不生成条目）"""
        try:
            import json
            chat_controller = self.app_controller.chat_controller
            conv_model = chat_controller.conversation_model
            conv_model._current_conversation_id = None
            conv_model._current_user_content = None
            # 重置累计 token/费用，确保 UI 同步归零
            chat_controller._session_total_tokens = 0
            chat_controller._session_total_cost = 0.0
            chat_controller.push_token_stats(0, 0, 0, 0.0, 0.0)
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
            conv_model._current_conversation_id = None
            conv_model._current_user_content = None
            # 重置累计 token/费用，确保 UI 同步归零
            chat_controller._session_total_tokens = 0
            chat_controller._session_total_cost = 0.0
            chat_controller.push_token_stats(0, 0, 0, 0.0, 0.0)
            data = conv_model.get_sidebar_data()
            welcome_html = '<div class="welcome-screen" id="welcomeScreen">' \
                '<div class="welcome-icon">🤖</div>' \
                '<h1 class="welcome-title">AI 智能助手</h1>' \
                '</div>'
            js = (
                f"document.getElementById('chatTitle').textContent='新对话';"
                f"document.getElementById('chatMessages').innerHTML={json.dumps(welcome_html)};"
                f"window.chatApp.messages=[];"
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
        """流式更新消息内容"""
        c = json.dumps(content)
        self.execute_js(f"window.onStreamUpdate({c});")

    def on_stream_complete(self):
        """流式响应完成"""
        self.execute_js("window.onStreamComplete();")

    def on_set_processing(self, processing: bool):
        """设置处理状态"""
        self.execute_js(f"window.onSetProcessing({str(processing).lower()});")

    def on_show_error(self, error_msg: str):
        """显示错误消息"""
        e = json.dumps(error_msg)
        self.execute_js(f"window.onShowError({e});")

    def on_add_tool_call(self, tool_name: str, arguments_json: str):
        """添加工具调用卡片"""
        n = json.dumps(tool_name)
        a = json.dumps(arguments_json)
        self.execute_js(f"window.onAddToolCall({n}, {a});")
