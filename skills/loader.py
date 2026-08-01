"""
技能加载器 - 动态加载技能模块（Python 类 + MD 文件）
"""
import os
import re
import importlib
import inspect
from typing import Dict, List, Optional, Type
from skills.base import BaseSkill
from skills.registry import SkillRegistry


class SkillLoader:
    """技能加载器 - 支持 Python 类加载和 MD 文件解析"""

    def __init__(self, md_dir: str = None, builtin_package: str = "skills.builtin"):
        if md_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            md_dir = os.path.join(base, "skills", "md")

        self.md_dir = md_dir
        self.builtin_package = builtin_package
        self.registry = SkillRegistry()
        # MD 技能解析缓存：{filepath: (mtime, skill_dict)}，文件未变更时复用解析结果
        self._md_cache: Dict[str, tuple] = {}

    # ---- Python 类加载 ----

    def load_builtin_skills(self) -> int:
        """加载内建技能包中的所有技能类"""
        count = 0
        try:
            pkg = importlib.import_module(self.builtin_package)
            pkg_path = os.path.dirname(pkg.__file__)
            for fname in sorted(os.listdir(pkg_path)):
                if fname.endswith(".py") and not fname.startswith("__"):
                    mod_name = fname[:-3]
                    full_mod = f"{self.builtin_package}.{mod_name}"
                    loaded = self._load_from_module(full_mod)
                    count += loaded
        except Exception as e:
            print(f"[SkillLoader] 加载内建技能失败: {e}")
        return count

    def load_custom_skills(self, custom_package: str = "skills.custom") -> int:
        """加载自定义技能"""
        count = 0
        try:
            pkg = importlib.import_module(custom_package)
            pkg_path = os.path.dirname(pkg.__file__)
            # 递归遍历所有子目录
            for root, dirs, files in os.walk(pkg_path):
                for fname in files:
                    if fname.endswith(".py") and not fname.startswith("__"):
                        rel_path = os.path.relpath(
                            os.path.join(root, fname), pkg_path
                        )
                        mod_path = rel_path.replace(os.sep, ".")[:-3]
                        full_mod = f"{custom_package}.{mod_path}"
                        loaded = self._load_from_module(full_mod)
                        count += loaded
        except Exception as e:
            print(f"[SkillLoader] 加载自定义技能失败: {e}")
        return count

    def _load_from_module(self, module_name: str) -> int:
        """从模块加载技能类"""
        count = 0
        try:
            mod = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(mod):
                if (inspect.isclass(obj)
                        and issubclass(obj, BaseSkill)
                        and obj is not BaseSkill
                        and not inspect.isabstract(obj)):
                    instance = obj()
                    if self.registry.register(instance):
                        count += 1
        except Exception:
            pass
        return count

    # ---- MD 文件加载 ----

    def parse_md_file(self, filepath: str) -> Optional[dict]:
        """解析单个 Markdown 技能文件"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None

        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if not match:
            name = os.path.splitext(os.path.basename(filepath))[0]
            return {
                "name": name,
                "enabled": True,
                "description": "",
                "content": content,
                "filepath": filepath,
            }

        yaml_block = match.group(1)
        body = match.group(2).strip()

        metadata = {
            "name": os.path.splitext(os.path.basename(filepath))[0],
            "enabled": True,
            "description": "",
        }
        for line in yaml_block.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key == "enabled":
                    metadata["enabled"] = value.lower() in ("true", "yes", "1")
                elif key == "name":
                    metadata["name"] = value
                elif key == "description":
                    metadata["description"] = value

        return {
            **metadata,
            "content": body,
            "filepath": filepath,
        }

    def _parse_md_file_cached(self, filepath: str) -> Optional[dict]:
        """带 mtime 缓存的 MD 文件解析：文件未变更时直接返回缓存，避免全量重复解析"""
        try:
            mtime = os.path.getmtime(filepath)
        except OSError:
            return None
        cached = self._md_cache.get(filepath)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        skill = self.parse_md_file(filepath)
        self._md_cache[filepath] = (mtime, skill)
        return skill

    def get_all_md_skills(self) -> list:
        """获取所有 MD 技能"""
        skills = []
        if not os.path.exists(self.md_dir):
            return skills
        for fname in sorted(os.listdir(self.md_dir)):
            if fname.endswith(".md"):
                fpath = os.path.join(self.md_dir, fname)
                skill = self._parse_md_file_cached(fpath)
                if skill:
                    skills.append(skill)
        return skills

    def get_enabled_md_skills(self) -> list:
        """获取所有已启用的 MD 技能"""
        return [s for s in self.get_all_md_skills() if s.get("enabled", True)]

    def load_md_skill_adapters(self) -> list:
        """将所有已启用的 MD 技能包装为可执行的 BaseSkill 适配器（统一技能模型）"""
        from skills.md_skill import MdSkill
        adapters = []
        for skill in self.get_enabled_md_skills():
            try:
                adapters.append(MdSkill(skill))
            except Exception as e:
                print(f"[SkillLoader] ⚠️ 包装 MD 技能失败 '{skill.get('name')}': {e}")
        return adapters

    def get_combined_prompt(self) -> str:
        """获取所有启用 MD 技能的合并提示词"""
        enabled = self.get_enabled_md_skills()
        if not enabled:
            return ""
        parts = ["\n\n## 技能指令", "请根据以下技能要求响应用户：\n"]
        for skill in enabled:
            parts.append(f"### {skill['name']}")
            if skill.get("description"):
                parts.append(f"> {skill['description']}")
            parts.append(skill.get("content", ""))
            parts.append("")
        return "\n".join(parts)