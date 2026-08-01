"""
SkillDispatcher - 技能调度器
将技能注册为 AI 可调用的工具，支持异步执行和 Tool 描述生成
"""
import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from skills.base import BaseSkill, SkillResult, DEFAULT_SKILL_TIMEOUT
from skills.context import SkillContext
from skills.registry import SkillRegistry


class SkillDispatcher:
    """
    Skill 调度器

    职责：
    1. 注册/注销 skill 实例
    2. 将 skill 格式化为 AI 可识别的 Tool 描述
    3. 异步执行 skill 调用，返回结果字符串
    4. 支持超时和错误处理

    数据源说明：
    技能的唯一数据源为 SkillRegistry（单例）。Dispatcher 不维护独立副本，
    运行时通过 SkillManager / Registry 动态注册或注销的技能可被即时感知，
    避免“双注册中心”状态不一致的问题。
    """

    def __init__(self, default_timeout: float = DEFAULT_SKILL_TIMEOUT):
        # 单一数据源：SkillRegistry 单例
        self.registry = SkillRegistry()
        # 记录由本调度器注册的技能名，clear() 时仅清理这些，不影响其他模块注册的技能
        self._registered: set = set()
        self._default_timeout = default_timeout
        # 执行历史（内存环形缓冲，最多保留 100 条），用于可观测性
        self.execution_history: deque = deque(maxlen=100)

    # ---- 注册管理 ----

    def register_skill(self, skill: BaseSkill) -> bool:
        """注册一个技能（注册到共享 SkillRegistry 单例）"""
        if not skill.name or not skill.enabled:
            return False
        if not self.registry.register(skill):
            return False
        self._registered.add(skill.name)
        return True

    def register_from_registry(self, registry) -> int:
        """从 SkillRegistry 批量注册"""
        count = 0
        for skill in registry.get_enabled():
            if self.register_skill(skill):
                count += 1
        return count

    def unregister_skill(self, name: str) -> bool:
        """注销技能"""
        self._registered.discard(name)
        return self.registry.unregister(name)

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取技能"""
        return self.registry.get(name)

    def get_all_skills(self) -> List[BaseSkill]:
        """获取所有已注册（已启用）技能"""
        return self.registry.get_enabled()

    def clear(self):
        """清除由本调度器注册的技能（不影响其他模块注册的技能）"""
        for name in list(self._registered):
            self.registry.unregister(name)
        self._registered.clear()

    @property
    def count(self) -> int:
        """已注册（已启用）技能数量"""
        return len(self.registry.get_enabled())

    # ---- Tool 描述生成 ----

    def get_tool_descriptions(self) -> List[Dict[str, Any]]:
        """
        生成 OpenAI/MCP 兼容的 Tool 描述列表

        返回格式:
        [
            {
                "type": "function",
                "function": {
                    "name": "skill_name",
                    "description": "技能描述",
                    "parameters": { ... }  # JSON Schema
                }
            },
            ...
        ]
        """
        tools = []
        for skill in self.registry.get_enabled():
            tool = self._skill_to_tool(skill)
            if tool:
                tools.append(tool)
        return tools


    def _skill_to_tool(self, skill: BaseSkill) -> Optional[Dict[str, Any]]:
        """将单个 skill 转换为 Tool 格式"""
        try:
            # 获取 input_schema（如果 skill 定义了的话）
            input_schema = getattr(skill, 'input_schema', None) or self._default_input_schema(skill)

            return {
                "type": "function",
                "function": {
                    "name": f"skill_{skill.name}",
                    "description": skill.description or f"执行 {skill.name} 技能",
                    "parameters": input_schema,
                }
            }
        except Exception as e:
            print(f"[SkillDispatcher] ⚠️ 生成 Tool 描述失败 '{skill.name}': {e}")
            return None

    def _default_input_schema(self, skill: BaseSkill) -> Dict[str, Any]:
        """为没有定义 input_schema 的 skill 生成默认 schema"""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": f"传递给 {skill.name} 技能的处理内容"
                }
            },
            "required": ["query"]
        }

    # ---- 技能执行 ----

    async def execute_skill(
        self,
        skill_name: str,
        arguments: Dict[str, Any],
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        异步执行 skill，返回结果字符串

        Args:
            skill_name: 技能名称
            arguments: 执行参数
            context: 执行上下文
            timeout: 超时秒数

        Returns:
            结果字符串（给 AI 看的内容）
        """
        skill = self.registry.get(skill_name)
        if not skill:
            self._record_execution(skill_name, False, error="未注册")
            return f"⚠️ 技能 '{skill_name}' 未注册"
        if not skill.enabled:
            self._record_execution(skill_name, False, error="已禁用")
            return f"⚠️ 技能 '{skill_name}' 已禁用"

        if context is None:
            context = SkillContext()
        else:
            # 复用传入的上下文，注入调度器引用
            context.skill_dispatcher = self

        # 注入参数到 context.params 和 context.variables
        context.params = dict(arguments)
        for key, value in arguments.items():
            context.set(key, value)

        _timeout = timeout if timeout is not None else self._default_timeout

        start = time.time()
        try:
            result = await asyncio.wait_for(
                skill.execute(context, **arguments),
                timeout=_timeout,
            )
            duration = (time.time() - start) * 1000
            result.duration_ms = duration
            skill._execution_count += 1
            self._record_execution(skill_name, result.success, error=result.error, duration_ms=result.duration_ms)

            # 格式化结果返回
            return self._format_result(skill_name, result)

        except asyncio.TimeoutError:
            self._record_execution(skill_name, False, error=f"执行超时 (>{_timeout}s)")
            return f"⚠️ 技能 '{skill_name}' 执行超时 (>{_timeout}s)"
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._record_execution(skill_name, False, error=str(e))
            return f"⚠️ 技能 '{skill_name}' 执行失败: {str(e)}"

    def _format_result(self, skill_name: str, result: SkillResult) -> str:
        """格式化执行结果为可读字符串"""
        if result.success:
            output_str = str(result.output) if result.output is not None else "（无输出）"
            return f"✅ 技能 '{skill_name}' 执行成功:\n{output_str}"
        else:
            error = result.error or "未知错误"
            return f"❌ 技能 '{skill_name}' 执行失败: {error}"

    # ---- 快捷执行 ----

    async def execute_by_name(
        self,
        skill_name: str,
        query: str = "",
        **kwargs
    ) -> str:
        """
        快捷执行：通过技能名称和 query 参数执行

        Args:
            skill_name: 技能名称
            query: 主要输入内容
            **kwargs: 额外参数
        """
        arguments = {"query": query, **kwargs}
        return await self.execute_skill(skill_name, arguments)

    def _record_execution(self, skill_name: str, success: bool,
                          error: Optional[str] = None, duration_ms: float = 0.0):
        """记录一次技能执行历史（内存环形缓冲）"""
        self.execution_history.append({
            "skill_name": skill_name,
            "success": success,
            "duration_ms": round(duration_ms, 3),
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

    def get_execution_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取执行历史（最近 limit 条，默认全部）"""
        items = list(self.execution_history)
        if limit is not None:
            items = items[-limit:]
        return items

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            "total_skills": self.count,
            "execution_history_count": len(self.execution_history),
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                    "enabled": s.enabled,
                }
                for s in self.registry.get_enabled()
            ],
        }
