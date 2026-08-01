"""
工具沙箱 - 安全执行工具
"""
import sys
import subprocess
import tempfile
import os
from typing import Any, Dict, Optional, Tuple


class ToolSandbox:
    """工具沙箱 - 安全地执行工具代码"""

    ALLOWED_MODULES = {
        "json", "math", "random", "datetime", "re", "collections",
        "itertools", "functools", "typing", "enum", "string",
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._temp_files = []

    def execute_python(self, code: str, timeout: int = 10) -> Tuple[bool, Any]:
        """沙箱中执行 Python 代码"""
        if not self.enabled:
            return False, "沙箱已禁用"

        # 检查导入模块是否在白名单中
        import ast
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[0] not in self.ALLOWED_MODULES:
                            return False, f"不允许导入模块: {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[0] not in self.ALLOWED_MODULES:
                        return False, f"不允许导入模块: {node.module}"
        except SyntaxError as e:
            return False, f"语法错误: {e}"

        # 在临时文件执行
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        tmp.write(code)
        tmp.close()
        self._temp_files.append(tmp.name)

        try:
            result = subprocess.run(
                [sys.executable, tmp.name],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "执行超时"
        except Exception as e:
            return False, str(e)

    def cleanup(self):
        """清理临时文件"""
        for f in self._temp_files:
            try:
                os.unlink(f)
            except (FileNotFoundError, PermissionError):
                pass
        self._temp_files.clear()