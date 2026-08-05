"""
技能加载器 - 动态加载技能模块（Python 类 + MD 技能目录）
MD 技能使用 Claude Skill 风格的目录化结构：

skills/md/
  <skill-name>/
    SKILL.md          # 必需：核心指令与元数据（YAML Frontmatter）
    scripts/          # 可选：可执行的脚本（.py, .sh）
    references/       # 可选：供 AI 参考的详细文档
    assets/           # 可选：模板、图片等静态资源
"""
import os
import re
import importlib
import inspect
from typing import Dict, List, Optional, Type
from skills.base import BaseSkill
from skills.registry import SkillRegistry


class SkillLoader:
    """技能加载器 - 支持 Python 类加载和 MD 技能目录解析"""

    # 技能内部可选子目录
    SKILL_SUBDIRS = ("scripts", "references", "assets")

    def __init__(self, md_dir: str = None, builtin_package: str = "skills.builtin"):
        if md_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            md_dir = os.path.join(base, "skills", "md")

        self.md_dir = md_dir
        self.builtin_package = builtin_package
        self.registry = SkillRegistry()
        # MD 技能解析缓存：{skill_filepath: (mtime, skill_dict)}，文件未变更时复用解析结果
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

    # ---- MD 技能目录解析 ----

    def _scan_subdir_files(self, skill_dir: str, subdir: str) -> list:
        """扫描技能目录下指定可选子目录中的文件，返回相对路径列表（跳过 __pycache__）"""
        files = []
        sub_path = os.path.join(skill_dir, subdir)
        if not os.path.isdir(sub_path):
            return files
        for root, dirs, fnames in os.walk(sub_path):
            # 跳过 Python 缓存目录
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in sorted(fnames):
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, skill_dir).replace(os.sep, "/")
                files.append(rel)
        return files

    def parse_md_file(self, filepath: str) -> Optional[dict]:
        """解析单个技能目录的 SKILL.md 文件，并扫描可选子目录资源

        参数 filepath 为 SKILL.md 的完整路径。
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None

        skill_dir = os.path.dirname(filepath)

        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if not match:
            # 无 YAML Frontmatter：使用目录名作为技能名
            name = os.path.basename(skill_dir)
            return {
                "name": name,
                "enabled": True,
                "description": "",
                "content": content,
                "filepath": filepath,
                "skill_dir": skill_dir,
                "scripts": self._scan_subdir_files(skill_dir, "scripts"),
                "references": self._scan_subdir_files(skill_dir, "references"),
                "assets": self._scan_subdir_files(skill_dir, "assets"),
            }

        yaml_block = match.group(1)
        body = match.group(2).strip()

        metadata = {
            "name": os.path.basename(skill_dir),
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
            "skill_dir": skill_dir,
            "scripts": self._scan_subdir_files(skill_dir, "scripts"),
            "references": self._scan_subdir_files(skill_dir, "references"),
            "assets": self._scan_subdir_files(skill_dir, "assets"),
        }

    def _parse_skill_dir_cached(self, skill_dir: str) -> Optional[dict]:
        """带 mtime 缓存的技能目录解析：SKILL.md 未变更时直接返回缓存"""
        skill_file = os.path.join(skill_dir, "SKILL.md")
        try:
            mtime = os.path.getmtime(skill_file)
        except OSError:
            return None
        cached = self._md_cache.get(skill_file)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        skill = self.parse_md_file(skill_file)
        self._md_cache[skill_file] = (mtime, skill)
        return skill

    def get_all_md_skills(self) -> list:
        """获取所有 MD 技能（仅支持目录化结构：skills/md/<name>/SKILL.md）"""
        skills = []
        if not os.path.exists(self.md_dir):
            return skills
        for name in sorted(os.listdir(self.md_dir)):
            skill_path = os.path.join(self.md_dir, name)
            if not os.path.isdir(skill_path):
                continue
            skill = self._parse_skill_dir_cached(skill_path)
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

    def _get_project_root(self) -> str:
        """项目根目录（skills/md 的上级的上级）"""
        return os.path.dirname(os.path.dirname(os.path.abspath(self.md_dir)))

    def _build_resource_full_path(self, skill: dict, rel_path: str) -> str:
        """资源路径自动补全为绝对路径"""
        if not skill:
            return rel_path
        try:
            skill_dir = skill.get("skill_dir", "")
            if not skill_dir:
                return rel_path
            return os.path.abspath(os.path.join(skill_dir, rel_path))
        except Exception:
            return rel_path

    def _expand_skill_content_paths(self, skill: dict, content: str) -> str:
        """将 SKILL.md 正文中出现的资源简写路径自动补全为项目根完整路径

        SKILL.md 中通常用简写（如 scripts/calculator.py，相对技能目录），
        此处将正文中出现的 scripts/ references/ assets/ 引用替换为完整路径
        （如 skills/md/calculator/scripts/calculator.py），使 AI 能直接执行。
        """
        if not content:
            return content
        # 收集正文中出现的所有资源简写路径
        for subdir in ("scripts", "references", "assets"):
            # 匹配 "subdir/文件名" 形式的路径引用，并保留前一个字符
            prefix, sep, rest = re.escape(subdir), "/", r"[\w./-]+"
            pattern = re.compile(r"(^|\s|\"|'|\(|\[|\{|`)" + prefix + sep + rest)
            def repl(m):
                return m.group(1) + self._build_resource_full_path(skill, m.group(0)[1:])
            content = pattern.sub(repl, content)
        return content

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
            # 正文中的资源简写路径自动补全为项目根完整路径
            content = self._expand_skill_content_paths(skill, skill.get("content", ""))
            parts.append(content)
            # 注入可参考的附加资源文件名（节省 token，AI 需要时再读取）
            # 路径自动补全为项目根相对完整路径，方便 AI 直接调用
            refs = skill.get("references", [])
            scripts = skill.get("scripts", [])
            assets = skill.get("assets", [])
            if refs:
                parts.append("> 可参考文档：")
                for r in refs:
                    parts.append(f"  - {self._build_resource_full_path(skill, r)}")
            if scripts:
                parts.append("> 可用脚本：")
                for s in scripts:
                    parts.append(f"  - {self._build_resource_full_path(skill, s)}")
            if assets:
                parts.append("> 附加资源：")
                for a in assets:
                    parts.append(f"  - {self._build_resource_full_path(skill, a)}")
            parts.append("")
        return "\n".join(parts)
