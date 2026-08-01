"""
会话管理 - 管理AI对话历史
"""
class SessionManager:
    def __init__(self):
        self._sessions = {}
    
    def create_session(self, session_id=None):
        import uuid
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = {'messages': [], 'created': __import__('time').time()}
        return sid
    
    def add_message(self, session_id, role, content):
        if session_id not in self._sessions:
            self.create_session(session_id)
        self._sessions[session_id]['messages'].append({'role': role, 'content': content})
    
    def get_messages(self, session_id):
        return self._sessions.get(session_id, {}).get('messages', [])
    
    def clear_session(self, session_id):
        if session_id in self._sessions:
            self._sessions[session_id]['messages'] = []