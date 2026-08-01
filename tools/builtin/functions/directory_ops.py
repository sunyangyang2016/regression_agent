"""
directory_ops — 目录操作工具

支持四种操作：
  - Readdir: 读取指定目录下的文件和子目录列表
  - Mkdir:   创建目录（递归创建多层目录）
  - Rmdir:   删除目录
  - Chdir:   查看/切换当前工作目录

可直接调用:
    directory_ops(action, path, recursive) -> str
"""
import os
import stat


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "directory_ops",
            "description": "目录操作工具 — 读取目录列表(Readdir)、创建目录(Mkdir)、删除目录(Rmdir)、查看/切换工作目录(Chdir)",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["Readdir", "Mkdir", "Rmdir", "Chdir"],
                        "description": "操作类型: Readdir=读取目录列表, Mkdir=创建目录, Rmdir=删除目录, Chdir=查看/切换工作目录"
                    },
                    "path": {
                        "type": "string",
                        "description": "目标目录路径。Chdir 时可选（不传则返回当前工作目录），其他操作必填。"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Rmdir 时：是否递归删除（慎用，会删除目录下所有内容）。Readdir 时：是否递归列出所有子目录内容。"
                    }
                },
                "required": ["action"]
            }
        },
        "display": {
            "name_cn": "目录操作",
            "description_cn": "读取目录列表、创建目录、删除目录、查看/切换工作目录",
            "icon": "fa-folder"
        }
    }
]

# 需要跨调用持久化的当前工作目录
_current_cwd = None


def _resolve_cwd(path=None):
    """解析目标目录：如传入了 path 则用 path，否则返回系统当前工作目录"""
    if path:
        return os.path.abspath(path)
    if _current_cwd:
        return _current_cwd
    return os.getcwd()


def _format_size(size: int) -> str:
    """格式化文件大小"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    else:
        return f"{size / 1024 / 1024 / 1024:.1f} GB"


def _do_readdir(target_path: str, recursive: bool = False, _depth: int = 0) -> str:
    """递归或非递归列出目录内容"""
    if not os.path.isdir(target_path):
        return f"❌ 路径不存在或不是目录: {target_path}"

    lines = []
    indent = "  " * _depth

    try:
        entries = sorted(os.listdir(target_path), key=lambda x: (not os.path.isdir(os.path.join(target_path, x)), x.lower()))
    except PermissionError:
        return f"❌ 无权限访问: {target_path}"
    except Exception as e:
        return f"❌ 读取失败: {e}"

    for entry in entries:
        full_path = os.path.join(target_path, entry)
        is_dir = os.path.isdir(full_path)
        is_link = os.path.islink(full_path)

        try:
            st = os.stat(full_path)
            size = st.st_size
            mtime = st.st_mtime
        except Exception:
            size = 0
            mtime = 0

        from datetime import datetime
        time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

        if is_dir:
            lines.append(f"{indent}📁 {entry}/    ({time_str})")
        elif is_link:
            try:
                target = os.readlink(full_path)
                lines.append(f"{indent}🔗 {entry} → {target}    ({_format_size(size)}, {time_str})")
            except Exception:
                lines.append(f"{indent}🔗 {entry}    ({_format_size(size)}, {time_str})")
        else:
            lines.append(f"{indent}📄 {entry}    ({_format_size(size)}, {time_str})")

    # 递归子目录
    if recursive:
        for entry in sorted(os.listdir(target_path), key=str.lower):
            full_path = os.path.join(target_path, entry)
            if os.path.isdir(full_path):
                sub = _do_readdir(full_path, recursive=True, _depth=_depth + 1)
                if sub and not sub.startswith("❌"):
                    lines.append("")
                    lines.append(sub)

    return "\n".join(lines)


def _do_mkdir(target_path: str) -> str:
    """创建目录（递归创建多层）"""
    if not target_path:
        return "❌ 请提供目录路径"
    try:
        os.makedirs(target_path, exist_ok=True)
        return f"✅ 已创建目录: {os.path.abspath(target_path)}"
    except PermissionError:
        return f"❌ 无权限创建目录: {target_path}"
    except Exception as e:
        return f"❌ 创建失败: {e}"


def _do_rmdir(target_path: str, recursive: bool = False) -> str:
    """删除目录"""
    if not target_path:
        return "❌ 请提供目录路径"
    if not os.path.exists(target_path):
        return f"❌ 路径不存在: {target_path}"

    abs_path = os.path.abspath(target_path)

    if not recursive:
        # 仅删除空目录
        try:
            os.rmdir(abs_path)
            return f"✅ 已删除空目录: {abs_path}"
        except OSError as e:
            if "directory not empty" in str(e).lower() or "目录非空" in str(e):
                return f"❌ 目录非空，如需递归删除请设置 recursive=true（慎用）"
            return f"❌ 删除失败: {e}"
        except Exception as e:
            return f"❌ 删除失败: {e}"
    else:
        # 递归删除（慎用！）
        try:
            import shutil
            shutil.rmtree(abs_path)
            return f"✅ 已递归删除目录及其所有内容: {abs_path}"
        except Exception as e:
            return f"❌ 递归删除失败: {e}"


def _do_chdir(path=None) -> str:
    """查看或切换当前工作目录"""
    global _current_cwd

    if path:
        # 切换到指定目录
        abs_path = os.path.abspath(path)
        if not os.path.isdir(abs_path):
            return f"❌ 路径不存在或不是目录: {abs_path}"
        _current_cwd = abs_path
        return f"✅ 当前工作目录已切换至: {abs_path}"
    else:
        # 查看当前工作目录
        cwd = _current_cwd or os.getcwd()
        return f"📍 当前工作目录: {cwd}"


def directory_ops(arguments: dict) -> str:
    """目录操作统一入口
    
    @param arguments: dict - 包含 action, path, recursive
        - action: str - 操作类型 (Readdir/Mkdir/Rmdir/Chdir)
        - path: str (可选) - 目标目录路径
        - recursive: bool (可选) - 是否递归
    @return str - 操作结果
    """
    if isinstance(arguments, str):
        import json
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return "❌ 参数格式错误，需要 JSON 对象"

    action = arguments.get("action", "").strip()
    path = arguments.get("path", "").strip() or None
    recursive = arguments.get("recursive", False)

    if not action:
        return "❌ 请提供 action 参数（Readdir/Mkdir/Rmdir/Chdir）"

    action = action.strip()

    if action == "Readdir":
        target = _resolve_cwd(path)
        return _do_readdir(target, recursive=recursive)

    elif action == "Mkdir":
        if not path:
            return "❌ Mkdir 操作需要提供 path 参数"
        return _do_mkdir(path)

    elif action == "Rmdir":
        if not path:
            return "❌ Rmdir 操作需要提供 path 参数"
        return _do_rmdir(path, recursive=recursive)

    elif action == "Chdir":
        return _do_chdir(path)

    else:
        return f"❌ 未知操作: {action}，支持的操作为 Readdir/Mkdir/Rmdir/Chdir"