"""
ConversationModel - 会话模型
管理会话数据与持久化逻辑（SQLite 数据库）
业务层面向业务实体（ChatSession / ChatMessage），经 Repository 持久化
"""
import uuid
import threading
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

from model.entities.chat_session import ChatSession
from model.entities.chat_message import ChatMessage


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
        from storage.repositories.conversation_repo import ConversationRepository
        from storage.repositories.message_repo import MessageRepository
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
        
        conv = ChatSession(
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

    def save_message(self, role: str, content: str, round_no: int = None, marker: str = None,
                     token_count: int = 0):
        """保存消息到数据库

        Args:
            role: 消息角色（user / assistant / tool）
            content: 消息内容
            round_no: 可选，AI 轮次序号（多轮工具调用时的轮次标记）
            marker: 可选，轮次标记（tool_call=工具调用轮 / final=最终完成轮）
            token_count: 该条消息对应的 token 数。assistant 消息为 API 返回的
                input+output 总 token（= 下一次发送前的 context 增量）；user 消息默认 0
        """
        if not self._current_conversation_id:
            return
        
        now = datetime.now()
        msg = ChatMessage(
            session_id=self._current_conversation_id,
            role=role,
            content=content,
            round_no=round_no,
            marker=marker,
            token_count=token_count,
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

    def load_conversation_messages(self, conversation_id: str, max_context: int = None):
        """加载指定对话的消息（AI 上下文用，应用滑动窗口限制）

        加载策略：
        1. system 日志（prompt）全部保留，始终放在最前
        2. 对话消息从最新往回逐条迭代，累加每条 token_count
           （assistant 的 token_count = input+output，代表了该轮 context 增量），
           直到超过 max_context × 90% 预算即停止（更旧的不返回）
        3. 重组：system（最前）+ 最新对话（后面）

        Args:
            conversation_id: 会话 ID
            max_context: 模型上下文最大容量，None 时默认 65536
        """
        # system 日志全部保留（数量少，一次取）
        system_msgs = self._msg_repo.find_system_by_conversation(conversation_id)

        # 从最新往回逐条迭代对话消息，累加 token_count，超预算即停
        budget = int((max_context or 65536) * 0.9)
        kept = []
        cumulative = 0
        for m in self._msg_repo.iter_dialogue(conversation_id, order="DESC"):
            tok = m.token_count or 0
            if kept and cumulative + tok > budget:
                break  # 超预算，不再取更旧的
            kept.insert(0, m)  # 保持时间正序
            cumulative += tok

        # 重组：system（最前）+ 最新对话（后面）
        result = system_msgs + kept

        self._current_conversation_id = conversation_id
        self._current_user_content = None
        self.current_conversation_changed.emit(conversation_id)

        return [
            {"role": m.role, "content": m.content, "time": m.created_at.isoformat() if m.created_at else ""}
            for m in result
        ]

    def load_latest_messages(self, conversation_id: str, offset: int = 0, limit: int = 100):
        """分页加载该会话最新对话消息（UI 显示用，不含 system prompt）

        Args:
            conversation_id: 会话 ID
            offset: 偏移量（0 = 最新一页；大于 0 表示加载更早的历史）
            limit: 每页条数

        Returns:
            [{role, content, time}, ...] 时间正序
        """
        msgs = self._msg_repo.find_latest_paged(conversation_id, offset=offset, limit=limit)
        return [
            {"role": m.role, "content": m.content, "time": m.created_at.isoformat() if m.created_at else ""}
            for m in msgs
        ]

    # ==========================================
    # 标题管理
    # ==========================================

    def get_token_count(self, conversation_id: str) -> int:
        """从数据库获取指定对话的累计 token 数（总计）"""
        with self._save_lock:
            conv = self._conv_repo.get(conversation_id)
            if conv:
                return conv.token_count or 0
            return 0

    def get_token_stats(self, conversation_id: str) -> dict:
        """从数据库获取指定对话的 token 分类统计

        Returns:
            {"hit": int, "miss": int, "output": int, "total": int}
        """
        with self._save_lock:
            conv = self._conv_repo.get(conversation_id)
            if conv:
                return {
                    "hit": conv.hit_token_count or 0,
                    "miss": conv.miss_token_count or 0,
                    "output": conv.output_token_count or 0,
                    "total": conv.token_count or 0,
                }
            return {"hit": 0, "miss": 0, "output": 0, "total": 0}

    def get_log_file(self, conversation_id: str) -> Optional[str]:
        """获取指定对话的 AI 通信日志文件路径（可能为 None）"""
        with self._save_lock:
            conv = self._conv_repo.get(conversation_id)
            if conv:
                return conv.log_file or None
            return None

    def update_log_file(self, log_file: str):
        """更新当前对话的 AI 通信日志文件路径到数据库"""
        if not self._current_conversation_id:
            return
        with self._save_lock:
            conv = self._conv_repo.get(self._current_conversation_id)
            if conv:
                conv.log_file = log_file
                conv.updated_at = datetime.now()
                self._conv_repo.save(conv)

    def update_token_count(self, token_count: int):
        """更新当前对话的累计 token 数（总计）到数据库"""
        if not self._current_conversation_id:
            return
        with self._save_lock:
            conv = self._conv_repo.get(self._current_conversation_id)
            if conv:
                conv.token_count = token_count
                conv.updated_at = datetime.now()
                self._conv_repo.save(conv)

    def update_token_stats(self, hit_tokens: int, miss_tokens: int, output_tokens: int):
        """更新当前对话的 token 分类统计到数据库

        - hit_token_count / miss_token_count / output_token_count 分别累计
        - token_count（总计）由三者之和推导，保证一致性
        """
        if not self._current_conversation_id:
            return
        with self._save_lock:
            conv = self._conv_repo.get(self._current_conversation_id)
            if conv:
                conv.hit_token_count = hit_tokens
                conv.miss_token_count = miss_tokens
                conv.output_token_count = output_tokens
                conv.token_count = hit_tokens + miss_tokens + output_tokens
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
        """获取侧边栏对话列表"""
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