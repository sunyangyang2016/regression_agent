"""
技能注册中心 - 管理所有技能的注册与查找
"""
from typing import Dict, List, Optional, Type
from skills.base import BaseSkill


class SkillRegistry:
    """技能注册中心 - 单例模式"""

    _instance = None
    _skills: Dict[str, BaseSkill] = {}
    # 可选事件通道（callable(event, data)），由外部（如 AppController）注入 EventBus.emit
    _event_sink = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, skill: BaseSkill, validate: bool = True) -> bool:
        """注册技能"""
        if not skill.name:
            return False
        if validate:
            from skills.validator import SkillValidator
            is_valid, errors = SkillValidator.validate_skill(skill)
            if not is_valid:
                print(f"[SkillRegistry] 技能注册失败 '{skill.name}': {errors}")
                return False
        self._skills[skill.name] = skill
        self._notify_lifecycle("on_load", skill)
        self._emit("skill:registered", {"name": skill.name, "enabled": skill.enabled})
        return True

    def set_event_sink(self, sink):
        """注入事件通道（如 EventBus.emit），用于技能生命周期可观测性"""
        self._event_sink = sink

    def toggle_enabled(self, name: str) -> bool:
        """运行时切换技能启用状态（触发 on_enable / on_disable 钩子）"""
        skill = self._skills.get(name)
        if not skill:
            return False
        skill.set_enabled(not bool(skill.enabled))
        self._emit("skill:toggle", {"name": name, "enabled": skill.enabled})
        return True

    def _emit(self, event: str, data: dict):
        """通过注入的事件通道发送事件（异常不影响注册/注销主流程）"""
        if self._event_sink is None:
            return
        try:
            self._event_sink(event, data)
        except Exception as e:
            print(f"[SkillRegistry] ⚠️ 事件发送失败 {event}: {e}")

    @staticmethod
    def _notify_lifecycle(hook: str, skill: BaseSkill):
        """调用技能生命周期钩子（异常不影响注册/注销主流程）"""
        try:
            getattr(skill, hook)()
        except Exception as e:
            print(f"[SkillRegistry] ⚠️ 技能 '{getattr(skill, 'name', '?')}' {hook} 异常: {e}")

    def unregister(self, name: str) -> bool:
        """注销技能"""
        if name in self._skills:
            skill = self._skills[name]
            del self._skills[name]
            self._notify_lifecycle("on_unload", skill)
            self._emit("skill:unregistered", {"name": name})
            return True
        return False

    def get(self, name: str) -> Optional[BaseSkill]:
        """根据名称获取技能"""
        return self._skills.get(name)

    def get_all(self) -> List[BaseSkill]:
        """获取所有已注册技能"""
        return list(self._skills.values())

    def get_enabled(self) -> List[BaseSkill]:
        """获取所有已启用的技能"""
        return [s for s in self._skills.values() if s.enabled]

    def get_by_category(self, category: str) -> List[BaseSkill]:
        """按类别获取技能"""
        return [s for s in self._skills.values() if s.category == category]

    def get_by_tag(self, tag: str) -> List[BaseSkill]:
        """按标签获取技能"""
        return [s for s in self._skills.values() if tag in s.tags]

    def clear(self):
        """清空注册中心"""
        self._skills.clear()

    @property
    def count(self) -> int:
        """已注册技能数量"""
        return len(self._skills)

    def contains(self, name: str) -> bool:
        """检查技能是否已注册"""
        return name in self._skills