"""
SkillBridge - 技能桥接
处理技能列表、管理等相关前后端交互
"""
import json
from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase


class SkillBridge(BridgeBase):
    """技能桥接 — 技能管理"""

    def _get_repo(self):
        try:
            from data.repositories.skill_repo import SkillRepository
            return SkillRepository()
        except Exception as e:
            print(f"[SkillBridge] ❌ 获取技能仓库失败: {e}")
            return None

    def _get_skill_mgr(self):
        if self.app_controller and hasattr(self.app_controller, 'skill_manager'):
            return self.app_controller.skill_manager
        return None

    def _get_skill_disp(self):
        """获取 SkillDispatcher（如果有）"""
        if self.app_controller and hasattr(self.app_controller, 'skill_dispatcher'):
            return self.app_controller.skill_dispatcher
        return None

    @pyqtSlot(result=str)
    def getSkills(self):
        """返回技能列表 JSON（统一数据源：优先委托 AppController 聚合）"""
        if self.app_controller and hasattr(self.app_controller, "_get_skills_data"):
            try:
                return json.dumps(self.app_controller._get_skills_data(), ensure_ascii=False)
            except Exception as e:
                print(f"[SkillBridge] ⚠️ 委托 _get_skills_data 失败: {e}")
        mgr = self._get_skill_mgr()
        python_skills = []
        md_skills = []

        if mgr:
            try:
                # 获取 Python 技能类（跳过已注册的 MD 适配器，MD 技能在下方单独列出）
                from skills.md_skill import MdSkill
                for s in mgr.registry.get_all():
                    if isinstance(s, MdSkill):
                        continue
                    python_skills.append({
                        "name": s.name,
                        "description": s.description,
                        "category": s.category,
                        "enabled": s.enabled,
                        "source": "python",
                        "version": s.version,
                        "tags": s.tags,
                    })
            except Exception as e:
                print(f"[SkillBridge] ⚠️ getSkills registry: {e}")

            try:
                # 获取 MD 技能
                for s in mgr.get_md_skills():
                    md_skills.append({
                        "name": s.get("name", ""),
                        "description": s.get("description", ""),
                        "category": "md",
                        "enabled": s.get("enabled", True),
                        "source": "markdown",
                        "version": "1.0.0",
                        "tags": [],
                    })
            except Exception as e:
                print(f"[SkillBridge] ⚠️ getSkills md: {e}")

        # 如果 registry 为空，尝试从仓库加载
        if not python_skills and not md_skills:
            try:
                repo = self._get_repo()
                if repo:
                    for s in repo.get_all():
                        python_skills.append({
                            "name": s.name,
                            "description": s.description,
                            "category": s.category,
                            "enabled": s.enabled,
                            "source": s.source or "python",
                            "version": "1.0.0",
                            "tags": [],
                        })
            except Exception as e:
                print(f"[SkillBridge] ⚠️ getSkills repo: {e}")

        result = python_skills + md_skills
        return json.dumps(result, ensure_ascii=False)

    @pyqtSlot(result=str)
    def getSkillStatus(self):
        """获取技能系统状态 JSON"""
        mgr = self._get_skill_mgr()
        disp = self._get_skill_disp()
        status = {
            "initialized": False,
            "python_skills": 0,
            "md_skills": 0,
            "registered_in_dispatcher": 0,
        }
        if mgr:
            status["initialized"] = mgr._initialized
            status["python_skills"] = mgr.registry.count
            status["md_skills"] = len(mgr.get_md_skills())
        if disp:
            status["registered_in_dispatcher"] = disp.count
        return json.dumps(status, ensure_ascii=False)

    def _sync_md_tools(self):
        """MD 技能变更后，将磁盘状态同步到 AI（注册/注销适配器与工具处理器）"""
        if self.app_controller and hasattr(self.app_controller, "_resync_md_skill_tools"):
            try:
                return self.app_controller._resync_md_skill_tools()
            except Exception as e:
                print(f"[SkillBridge] ⚠️ 同步 MD 技能到 AI 失败: {e}")
        return 0

    def _refresh_frontend(self):
        """技能变更后刷新前端（统一走 AppController._sync_skills_to_frontend）"""
        if self.app_controller and hasattr(self.app_controller, "_sync_skills_to_frontend"):
            try:
                self.app_controller._sync_skills_to_frontend()
            except Exception as e:
                print(f"[SkillBridge] ⚠️ 刷新前端失败: {e}")

    @pyqtSlot(str)
    @pyqtSlot(str, str, str, result=bool)
    def on_upload_md(self, name, description, content):
        """上传 MD 技能文件（持久化到 skills/md/*.md）"""
        mgr = self._get_skill_mgr()
        if not mgr:
            return False
        ok = mgr.add_md_skill(name, description or "", content or "")
        if ok:
            self._sync_md_tools()
        self._refresh_frontend()
        return ok

    def on_add_skill(self, name):
        mgr = self._get_skill_mgr()
        if mgr:
            mgr.on_add_skill(name)
            self._sync_md_tools()
            self._refresh_frontend()

    @pyqtSlot(str)
    def on_remove_skill(self, name):
        mgr = self._get_skill_mgr()
        if mgr:
            mgr.on_remove_skill(name)
            self._sync_md_tools()
            self._refresh_frontend()

    @pyqtSlot(str)
    def on_toggle_skill(self, name):
        mgr = self._get_skill_mgr()
        if mgr:
            mgr.on_toggle_skill(name)
            self._sync_md_tools()
            self._refresh_frontend()
