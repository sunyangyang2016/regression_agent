"""
上下文管理 - 注入技能、工具描述到AI上下文
"""
class ContextManager:
    def __init__(self, skill_manager=None, tool_manager=None):
        self.skill_mgr = skill_manager
        self.tool_mgr = tool_manager
    
    def build_system_prompt(self, base_prompt=""):
        parts = [base_prompt]
        if self.skill_mgr:
            sp = getattr(self.skill_mgr, 'get_combined_prompt', lambda: '')()
            if sp:
                parts.append(sp)
        return "\n\n".join(filter(None, parts))