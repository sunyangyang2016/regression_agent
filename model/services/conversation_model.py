"""
ConversationModel - 会话模型
管理会话数据与持久化逻辑（SQLite 数据库）
"""
import uuid
import threading
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

from model.entities.conversation import ConversationModel as ConversationEntity
from model.entities.message import MessageModel as MessageEntity


class ConversationModel(QObject):
    """会话模型（SQLite 持久化）"""

    conversation_list_changed = pyqtSignal(list)
    current_conversation_changed = pyqtSignal(str)
    message_added = pyqtSignal(str, str, str)
    title_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_conversation_id: Optional[str] = None
        self._current_user_content: Optional[str] = None
        self._save_lock = threading.Lock()
        # Lazy import to avoid circular import
        from data.repositories.conversation_repo import ConversationRepository
        from data.repositories.message_repo import MessageRepository
        self._conv_repo = ConversationRepository()
        self._msg_repo = MessageRepository()

    # ==========================================
    # 对话管理
    # ==========================================

    def ensure_conversation(self, model_name="deepseek-chat"):
        """确保有当前对话，没有则创建"""
        if self._current_conversation_id:
            return
        
        conv_id = str(uuid.uuid4())
        now = datetime.now()
        
        conv = ConversationEntity(
            id=conv_id,
            title="新对话",
            model=model_name,
            message_count=0,
            token_count=0,
            created_at=now,
            updated_at=now,
            status="active"
        )
        with self._save_lock:
            self._conv_repo.save(conv)
        
        self._current_conversation_id = conv_id
        self.conversation_list_changed.emit(self._get_sidebar_data())
        self.current_conversation_changed.emit(conv_id)

    def delete_conversation(self, conversation_id: str):
        """删除指定对话及其消息"""
        with self._save_lock:
            for msg in self._msg_repo.find_by_conversation(conversation_id):
                self._msg_repo.delete(msg.id)
            self._conv_repo.delete(conversation_id)
        self.conversation_list_changed.emit(self._get_sidebar_data())

    # ==========================================
    # 消息管理
    # ==========================================

    def save_message(self, role: str, content: str):
        """保存消息到数据库"""
        if not self._current_conversation_id:
            return
        
        now = datetime.now()
        msg = MessageEntity(
            conversation_id=self._current_conversation_id,
            role=role,
            content=content,
            created_at=now
        )
        with self._save_lock:
            self._msg_repo.save(msg)
            # 更新对话的消息计数
            conv = self._conv_repo.get(self._current_conversation_id)
            if conv:
                conv.message_count = (conv.message_count or 0) + 1
                conv.updated_at = now
                self._conv_repo.save(conv)
        
        self.message_added.emit(self._current_conversation_id, role, content)

    def load_conversation_messages(self, conversation_id: str):
        """加载指定对话的所有消息"""
        with self._save_lock:
            msgs = self._msg_repo.find_by_conversation(conversation_id)
        
        self._current_conversation_id = conversation_id
        self._current_user_content = None
        self.current_conversation_changed.emit(conversation_id)
        
        return [
            {"role": m.role, "content": m.content, "time": m.created_at.isoformat() if m.created_at else ""}
            for m in msgs
        ]

    # ==========================================
    # 标题管理
    # ==========================================

    def get_token_count(self, conversation_id: str) -> int:
        """从数据库获取指定对话的累计 token 数"""
        with self._save_lock:
            conv = self._conv_repo.get(conversation_id)
            if conv:
                return conv.token_count or 0
            return 0

    def update_token_count(self, token_count: int):
        """更新当前对话的累计 token 数到数据库"""
        if not self._current_conversation_id:
            return
        with self._save_lock:
            conv = self._conv_repo.get(self._current_conversation_id)
            if conv:
                conv.token_count = token_count
                from datetime import datetime
                conv.updated_at = datetime.now()
                self._conv_repo.save(conv)

    def update_title(self, first_message: str):
        """根据首条消息更新对话标题"""
        if not self._current_conversation_id:
            return
        
        with self._save_lock:
            conv = self._conv_repo.get(self._current_conversation_id)
            if not conv or conv.title != "新对话":
                return
            
            title_bytes = first_message.encode('utf-8')[:16]
            title = title_bytes.decode('utf-8', errors='ignore')
            if title != first_message:
                title = title.rstrip() + "..."
            
            conv.title = title
            self._conv_repo.save(conv)
        
        self.title_changed.emit(self._current_conversation_id, title)
        self.conversation_list_changed.emit(self._get_sidebar_data())

    # ==========================================
    # 列表/侧边栏
    # ==========================================

    def get_sidebar_data(self):
        return self._get_sidebar_data()

    def _get_sidebar_data(self):
        """获取侧边栏对话列表（直接查 SQLite）"""
        with self._save_lock:
            all_convs = self._conv_repo.get_all()
        
        data = []
        for conv in all_convs:
            data.append({
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else "",
                "message_count": conv.message_count or 0
            })
        data.reverse()
        return data

    # ==========================================
    # 属性
    # ==========================================

    @property
    def current_conversation_id(self):
        return self._current_conversation_id

    @current_conversation_id.setter
    def current_conversation_id(self, value):
        self._current_conversation_id = value

    @property
    def current_user_content(self):
        return self._current_user_content

    @current_user_content.setter
    def current_user_content(self, value):
        self._current_user_content = value