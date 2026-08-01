"""
技能管理器 - 技能系统统一入口（Facade 门面模式）
整合加载、注册、执行、验证、MD 管理等功能
"""
import os
import json
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSlot
from skills.base import BaseSkill, SkillResult
from skills.context import SkillContext
from skills.registry import SkillRegistry
from skills.loader import SkillLoader
from skills.executor import SkillExecutor
from skills.validator import SkillValidator


class SkillManager(QObject):
    """技能管理器 - 统一管理所有技能操作"""

    def __init__(self, webview_or_md_dir=None, md_dir: str = None, parent=None):
        super().__init__(parent)
        # 兼容旧 API: SkillManager(webview) 或 SkillManager(md_dir) 或 SkillManager()
        if md_dir is None and isinstance(webview_or_md_dir, str):
            md_dir = webview_or_md_dir
            self.webview = None
        else:
            self.webview = webview_or_md_dir if not isinstance(webview_or_md_dir, str) else None
            if self.webview is not None:
                md_dir = md_dir

        self.registry = SkillRegistry()
        self.loader = SkillLoader(md_dir)
        self.executor = SkillExecutor()
        self.validator = SkillValidator()
        self._initialized = False
        self._cached_skills = []

        if self.webview:
            self._sync_to_js()
    
    # ---- 旧 API 兼容方法（前端 QWebChannel 桥接） ----
    
    def _sync_to_js(self):
        """同步技能数据到前端 JS（写入 appState.skills，与 AppController 推送路径一致）"""
        if not self.webview:
            return
        skills_json = json.dumps(self.get_skills_for_js())
        js = f"""
        if (typeof appState !== 'undefined') {{
            appState.skills = {skills_json};
            if (typeof renderSkills === 'function') renderSkills();
        }}
        """
        self.webview.page().runJavaScript(js)

    def add_token_count(self, count: int):
        """增加 Token 计数"""
        if not self.webview:
            return
        js = f"""
        if (window.state) {{
            window.state.tokenValue += {count};
            if (window.renderAll) window.renderAll();
        }}
        """
        self.webview.page().runJavaScript(js)

    @pyqtSlot(str)
    def on_add_skill(self, name: str):
        """前端调用：添加技能"""
        success = self.add_md_skill(name, "", "")
        if success:
            self._sync_to_js()
            self._add_message(f'✅ 技能 "{name}" 已添加。', 'agent')
        else:
            self._add_message(f'⚠️ 技能 "{name}" 已存在或名称无效。', 'agent')

    @pyqtSlot(str)
    def on_remove_skill(self, name: str):
        """前端调用：删除技能"""
        success = self.remove_md_skill(name)
        if success:
            self._sync_to_js()
            self._add_message(f'🗑️ 技能 "{name}" 已删除。', 'agent')

    @pyqtSlot(str)
    def on_toggle_skill(self, name: str):
        """前端调用：切换技能状态"""
        skill = self.loader.parse_md_file(
            os.path.join(self.loader.md_dir, f"{name}.md")
        )
        if skill:
            was_enabled = skill.get("enabled", True)
            self.toggle_md_skill(name)
            self._sync_to_js()
            status = "启用" if not was_enabled else "禁用"
            self._add_message(f'🔄 技能 "{name}" 已{status}。', 'agent')

    def _add_message(self, content: str, role: str = 'agent'):
        """添加消息到对话"""
        if not self.webview:
            return
        safe_content = json.dumps(content)
        safe_role = json.dumps(role)
        js = f"""
        if (typeof window.chat !== 'undefined' && typeof window.chat.addMessage === 'function') {{
            window.chat.addMessage({safe_content}, {safe_role});
        }}
        """
        self.webview.page().runJavaScript(js)

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

    # ---- MD 技能管理 ----

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


    def add_md_skill(self, name: str, description: str = "", content: str = "") -> bool:
        """添加 MD 技能文件"""
        filepath = os.path.join(self.loader.md_dir, f"{name}.md")
        if os.path.exists(filepath):
            return False

        md_content = (
            f"---\nname: {name}\nenabled: true\n"
            f"description: {description}\n---\n\n"
            f"{content or f'# {name}\n\n（请在此编写技能提示词）'}\n"
        )
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
            return True
        except Exception as e:
            print(f"[SkillManager] 创建 MD 技能失败: {e}")
            return False

    def remove_md_skill(self, name: str) -> bool:
        """删除 MD 技能文件"""
        filepath = os.path.join(self.loader.md_dir, f"{name}.md")
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception as e:
            print(f"[SkillManager] 删除 MD 技能失败: {e}")
        return False

    def toggle_md_skill(self, name: str) -> bool:
        """切换 MD 技能的启用状态"""
        import re
        filepath = os.path.join(self.loader.md_dir, f"{name}.md")
        skill = self.loader.parse_md_file(filepath)
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
            return True
        except Exception as e:
            print(f"[SkillManager] 切换技能状态失败: {e}")
            return False

    # ---- 前端桥接 ----

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