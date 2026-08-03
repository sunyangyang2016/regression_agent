"""
SkillBridge - 技能桥接
处理技能列表、管理等相关前后端交互
"""
import json
from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase


class SkillBridge(BridgeBase):
    """技能桥接 — 技能管理（技能数据由文件系统加载，不写入数据库）"""

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
                    meta = {}
                    try:
                        meta = s.get_metadata()
                    except Exception:
                        pass
                    python_skills.append({
                        "name": s.name,
                        "description": s.description,
                        "category": s.category,
                        "enabled": s.enabled,
                        "source": "python",
                        "version": s.version,
                        "tags": s.tags,
                        "detail": {
                            "version": s.version,
                            "category": s.category,
                            "priority": meta.get("priority"),
                            "tags": s.tags,
                            "input_schema": meta.get("input_schema"),
                            "triggers": meta.get("triggers"),
                            "execution_count": meta.get("execution_count"),
                            "created_at": meta.get("created_at"),
                        },
                    })
            except Exception as e:
                print(f"[SkillBridge] ⚠️ getSkills registry: {e}")

            try:
                # 获取 MD 技能
                from skills.manager import PROTECTED_MD_SKILLS
                for s in mgr.get_md_skills():
                    md_skills.append({
                        "name": s.get("name", ""),
                        "description": s.get("description", ""),
                        "category": "md",
                        "enabled": s.get("enabled", True),
                        "source": "markdown",
                        "version": "1.0.0",
                        "tags": [],
                        "protected": s.get("name", "") in PROTECTED_MD_SKILLS,
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
            except Exception as e:
                print(f"[SkillBridge] ⚠️ getSkills md: {e}")

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

    @pyqtSlot(str, str, result=bool)
    def on_upload_skill_dir(self, name, files_json):
        """上传技能目录（目录化结构）

        参数：
            name:      技能名称（目录名）
            files_json: JSON 字符串，格式 {"相对路径": "文件内容", ...}，必须包含 SKILL.md
        """
        mgr = self._get_skill_mgr()
        if not mgr:
            return False
        try:
            files = json.loads(files_json)
            if not isinstance(files, dict):
                return False
        except Exception as e:
            print(f"[SkillBridge] ⚠️ 解析上传目录 JSON 失败: {e}")
            return False

        ok = mgr.add_md_skill(name, files)
        if ok:
            self._sync_md_tools()
        self._refresh_frontend()
        return ok

    @pyqtSlot(str)
    def on_add_skill(self, name):
        """添加简单技能（仅创建 SKILL.md）"""
        mgr = self._get_skill_mgr()
        if mgr:
            mgr.add_md_skill(name, {"SKILL.md": f"# {name}\n\n（技能提示词正文）\n"})
            self._sync_md_tools()
            self._refresh_frontend()

    @pyqtSlot(str)
    def on_remove_skill(self, name):
        mgr = self._get_skill_mgr()
        if mgr:
            mgr.remove_md_skill(name)
            self._sync_md_tools()
            self._refresh_frontend()

    @pyqtSlot(str)
    def on_toggle_skill(self, name):
        mgr = self._get_skill_mgr()
        if mgr:
            mgr.toggle_md_skill(name)
            self._sync_md_tools()
            self._refresh_frontend()
