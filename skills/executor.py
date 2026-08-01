"""
技能执行器 - 负责执行已注册的技能，支持超时控制和结果收集
"""
import asyncio
import time
from typing import Any, Dict, Optional
from skills.base import BaseSkill, SkillResult, DEFAULT_SKILL_TIMEOUT
from skills.context import SkillContext
from skills.registry import SkillRegistry


class SkillExecutor:
    """技能执行器"""

    def __init__(self, default_timeout: float = DEFAULT_SKILL_TIMEOUT):
        self.registry = SkillRegistry()
        self.default_timeout = default_timeout

    async def execute(
        self,
        skill_name: str,
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> SkillResult:
        """执行指定名称的技能"""
        skill = self.registry.get(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"技能 '{skill_name}' 未找到",
            )
        if not skill.enabled:
            return SkillResult(
                success=False,
                error=f"技能 '{skill_name}' 已禁用",
            )

        if context is None:
            context = SkillContext()

        _timeout = timeout if timeout is not None else self.default_timeout

        start = time.time()
        try:
            result = await asyncio.wait_for(
                skill.execute(context, **kwargs),
                timeout=_timeout,
            )
            result.duration_ms = (time.time() - start) * 1000
            skill._execution_count += 1
            return result
        except asyncio.TimeoutError:
            return SkillResult(
                success=False,
                error=f"技能 '{skill_name}' 执行超时 (>{_timeout}s)",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"技能 '{skill_name}' 执行失败: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def execute_all(
        self,
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Dict[str, SkillResult]:
        """并发执行所有已启用的技能（每个技能使用独立上下文，避免串扰）"""
        skills = self.registry.get_enabled()
        if not skills:
            return {}
        base_ctx = context or SkillContext()
        tasks = [
            self.execute(s.name, self._isolate_context(base_ctx), timeout, **kwargs)
            for s in skills
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        results = {}
        for skill, res in zip(skills, results_list):
            if isinstance(res, SkillResult):
                results[skill.name] = res
            else:
                results[skill.name] = SkillResult(success=False, error=str(res))
        return results

    async def execute_by_category(
        self,
        category: str,
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Dict[str, SkillResult]:
        """并发执行指定类别的所有已启用技能"""
        skills = [s for s in self.registry.get_by_category(category) if s.enabled]
        if not skills:
            return {}
        base_ctx = context or SkillContext()
        tasks = [
            self.execute(s.name, self._isolate_context(base_ctx), timeout, **kwargs)
            for s in skills
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        results = {}
        for skill, res in zip(skills, results_list):
            if isinstance(res, SkillResult):
                results[skill.name] = res
            else:
                results[skill.name] = SkillResult(success=False, error=str(res))
        return results

    @staticmethod
    def _isolate_context(context: Optional[SkillContext]) -> SkillContext:
        """为每次执行创建独立上下文，隔离 variables/params，避免并发串扰"""
        if context is None:
            return SkillContext()
        import dataclasses
        return dataclasses.replace(
            context,
            variables={},
            params={},
        )
