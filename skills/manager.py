"""
技能管理器 - 技能系统统一入口（Facade 门面模式）
整合加载、注册、执行、验证、MD 技能目录管理等功能
"""
import os
import json
from typing import Any, Dict, List, Optional

from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext
from skills.registry import SkillRegistry
from skills.loader import SkillLoader
from skills.executor import SkillExecutor
from skills.validator import SkillValidator


# 受保护的内置 MD 技能（禁止删除、禁止上传同名覆盖）
PROTECTED_MD_SKILLS = {"mcp-server-install"}


class SkillManager:
    """技能管理器 - 统一管理所有技能操作"""

    def __init__(self, md_dir: str = None):
        self.registry = SkillRegistry()
        self.loader = SkillLoader(md_dir)
        self.executor = SkillExecutor()
        self.validator = SkillValidator()
        self._initialized = False
        self._cached_skills = []

    # ---- 生命周期 ----

    def initialize(self) -> bool:
        """初始化技能系统：加载内建和自定义技能"""
        if self._initialized:
            return True

        # 加载 Python 技能类
        builtin_count = self.loader.load_builtin_skills()
        custom_count = self.loader.load_custom_skills()

        self._initialized = True
        total = self.registry.count
        print(f"[SkillManager] 技能系统初始化完成: {total} 个技能"
              f" (内建 {builtin_count}, 自定义 {custom_count})")
        return True

    # ---- 技能执行 ----

    async def execute(
        self,
        skill_name: str,
        context: Optional[SkillContext] = None,
        **kwargs
    ) -> SkillResult:
        """执行指定技能"""
        return await self.executor.execute(skill_name, context, **kwargs)

    # ---- 注册管理 ----

    def register(self, skill: BaseSkill) -> bool:
        """注册一个技能"""
        is_valid, errors = self.validator.validate_skill(skill)
        if not is_valid:
            print(f"[SkillManager] 技能注册失败 '{skill.name}': {errors}")
            return False
        return self.registry.register(skill)

    def unregister(self, name: str) -> bool:
        """注销一个技能"""
        return self.registry.unregister(name)

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取技能"""
        return self.registry.get(name)

    def get_all_skills(self) -> List[BaseSkill]:
        """获取所有技能"""
        return self.registry.get_all()

    def get_enabled_skills(self) -> List[BaseSkill]:
        """获取已启用的技能"""
        return self.registry.get_enabled()

    # ---- MD 技能目录管理 ----

    def get_md_skills(self) -> list:
        """获取所有 MD 技能"""
        return self.loader.get_all_md_skills()

    def get_enabled_md_skills(self) -> list:
        """获取已启用的 MD 技能"""
        return self.loader.get_enabled_md_skills()

    def get_combined_prompt(self) -> str:
        """获取所有启用 MD 技能的合并提示词"""
        return self.loader.get_combined_prompt()

    def sync_md_skills_to_registry(self) -> int:
        """将磁盘上已启用的 MD 技能同步到 SkillRegistry（注册为可执行适配器）

        上传 / 删除 / 启用切换后调用，保证 AI 可即时感知 MD 技能状态：
        先移除当前已注册的 MD 适配器，再按磁盘上的实际状态重新注册。
        """
        from skills.md_skill import MdSkill
        # 1. 先移除已注册的 MD 适配器，确保与磁盘状态一致（避免“删除/禁用后仍可被 AI 调用”）
        for skill in list(self.registry.get_all()):
            if isinstance(skill, MdSkill):
                self.registry.unregister(skill.name)
        # 2. 重新注册磁盘上所有已启用的 MD 技能
        count = 0
        for adapter in self.loader.load_md_skill_adapters():
            existing = self.registry.get(adapter.name)
            if existing is not None:
                print(f"[SkillManager] ⚠️ 跳过 MD 技能 '{adapter.name}': 与已注册技能重名")
                continue
            if self.registry.register(adapter):
                count += 1
        return count

    def add_md_skill(self, name: str, files: dict) -> bool:
        """添加 MD 技能目录（目录化结构）

        参数：
            name:  技能名称（目录名）
            files: {相对路径: 文件内容} 字典，必须包含 SKILL.md
        """
        import shutil
        if not name or not isinstance(files, dict) or "SKILL.md" not in files:
            print("[SkillManager] 添加 MD 技能失败: 缺少 SKILL.md 或参数无效")
            return False

        # ===== 重名校验 =====
        # 1. 与内置保护技能重名 → 拒绝
        if name in PROTECTED_MD_SKILLS:
            print(f"[SkillManager] ⛔ 内置技能名 '{name}' 不允许作为上传名称")
            return False
        # 2. 与已存在的技能（Python 技能 + 已注册的 MD 技能）重名 → 拒绝
        existing_names = set()
        try:
            existing_names |= {s.name for s in self.registry.get_all()}
        except Exception:
            pass
        try:
            existing_names |= {md.get("name", "") for md in self.get_md_skills()}
        except Exception:
            pass
        if name in existing_names:
            print(f"[SkillManager] ⛔ 技能名 '{name}' 已存在，禁止重复上传")
            return False

        skill_dir = os.path.join(self.loader.md_dir, name)
        if os.path.exists(skill_dir):
            return False

        try:
            base_real = os.path.realpath(skill_dir) + os.sep
            for rel_path, content in files.items():
                # 防路径穿越：规范化并确保仍位于技能目录内
                full_path = os.path.realpath(os.path.join(skill_dir, rel_path))
                if full_path != os.path.realpath(skill_dir) and not full_path.startswith(base_real):
                    print(f"[SkillManager] ⚠️ 跳过非法路径: {rel_path}")
                    continue
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(str(content))
            return True
        except Exception as e:
            print(f"[SkillManager] 创建 MD 技能目录失败: {e}")
            shutil.rmtree(skill_dir, ignore_errors=True)
            return False

    def remove_md_skill(self, name: str) -> bool:
        """删除 MD 技能目录（递归）；受保护的内置技能禁止删除"""
        import shutil
        if name in PROTECTED_MD_SKILLS:
            print(f"[SkillManager] ⛔ {name} 是内置保护技能，禁止删除")
            return False
        skill_dir = os.path.join(self.loader.md_dir, name)
        try:
            if os.path.isdir(skill_dir):
                shutil.rmtree(skill_dir)
                return True
        except Exception as e:
            print(f"[SkillManager] 删除 MD 技能目录失败: {e}")
        return False

    def toggle_md_skill(self, name: str) -> bool:
        """切换 MD 技能的启用状态（修改 SKILL.md 中的 enabled 字段）"""
        import re
        filepath = os.path.join(self.loader.md_dir, name, "SKILL.md")
        skill = self.loader._parse_skill_dir_cached(os.path.dirname(filepath))
        if not skill:
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            new_enabled = "false" if skill.get("enabled", True) else "true"
            content = re.sub(
                r'^enabled:\s*(true|false)',
                f"enabled: {new_enabled}",
                content,
                flags=re.MULTILINE
            )
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            # 清除该文件的 mtime 缓存，确保后续重新解析最新状态
            self.loader._md_cache.pop(filepath, None)
            return True
        except Exception as e:
            print(f"[SkillManager] 切换技能状态失败: {e}")
            return False

    # ---- 前端数据 ----

    def get_skills_for_js(self) -> list:
        """获取前端格式的技能列表（统一数据源：Python 技能 + MD 技能）"""
        from skills.md_skill import MdSkill
        result = []
        for s in self.registry.get_all():
            # MD 技能已注册为 MdSkill 适配器，避免与下方 MD 文件列表重复显示
            if isinstance(s, MdSkill):
                continue
            result.append({
                "name": s.name,
                "enabled": s.enabled,
                "description": s.description,
                "category": s.category,
                "source": "python",
                "version": s.version,
                "tags": list(s.tags),
            })
        for s in self.get_md_skills():
            result.append({
                "name": s.get("name", ""),
                "enabled": s.get("enabled", True),
                "description": s.get("description", ""),
                "category": "md",
                "source": "markdown",
                "version": "1.0.0",
                "tags": [],
                "detail": {
                    "content": s.get("content", ""),
                    "filepath": s.get("filepath", ""),
                    "skill_dir": s.get("skill_dir", ""),
                    "scripts": s.get("scripts", []),
                    "references": s.get("references", []),
                    "assets": s.get("assets", []),
                    "version": "1.0.0",
                    "category": "md",
                },
            })
        return result

    def get_status(self) -> Dict[str, Any]:
        """获取技能系统状态"""
        return {
            "initialized": self._initialized,
            "python_skills": self.registry.count,
            "md_skills": len(self.get_md_skills()),
            "enabled_python": len(self.registry.get_enabled()),
            "enabled_md": len(self.get_enabled_md_skills()),
        }