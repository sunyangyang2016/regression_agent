"""
file_ops — 文件操作工具

支持九种操作：
  - Create:   创建新文件并写入内容，设置初始元数据（权限、时间戳）
  - Delete:   删除文件，释放磁盘空间
  - Copy:     复制文件或目录到目标位置
  - Read:     读取指定文件的内容，支持偏移和长度
  - Write:    写入内容到指定文件，支持指定偏移位置
  - Open:     在内存中建立文件控制块（FCB），返回文件描述符（fd）
  - Close:    释放内存中的文件描述符，将缓冲数据刷入磁盘
  - Rename:   修改文件的路径名
  - Truncate: 清空文件内容或将文件长度裁剪到指定大小

可直接调用:
    file_ops(action, path, ...) -> str
"""
import os
import time
import stat
import shutil


# ==========================================
# 文件描述符表（跨调用持久化）
# ==========================================
# fd 表结构: { fd: {"path": str, "mode": str, "opened_at": float, "file": file_object} }
_open_fds = {}
_next_fd = 3  # 0=stdin, 1=stdout, 2=stderr


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_ops",
            "description": "文件操作工具 — 创建(Create)、删除(Delete)、复制(Copy)、读取(Read)、写入(Write)、打开(Open)、关闭(Close)、重命名(Rename)、截断(Truncate)",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["Create", "Delete", "Copy", "Read", "Write", "Open", "Close", "Rename", "Truncate"],
                        "description": "操作类型"
                    },
                    "path": {
                        "type": "string",
                        "description": "目标文件路径（Create/Delete/Read/Write/Open/Rename/Truncate 时必填）"
                    },
                    "source": {
                        "type": "string",
                        "description": "Copy 操作时的源文件或目录路径"
                    },
                    "dest": {
                        "type": "string",
                        "description": "Copy 操作时的目标路径"
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Rename 操作时的新路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "Create/Write 操作时的文件内容"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Read/Write 操作时的字节偏移位置（Read从0开始，Write时-1=覆盖整个文件）"
                    },
                    "length": {
                        "type": "integer",
                        "description": "Read 操作时读取的字节数（可选，不填则读取到末尾）"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["r", "w", "a"],
                        "description": "Open 操作时的打开模式：r=只读, w=写入, a=追加"
                    },
                    "fd": {
                        "type": "integer",
                        "description": "Close 操作时：要关闭的文件描述符编号（来自 Open 返回）"
                    },
                    "size": {
                        "type": "integer",
                        "description": "Truncate 操作时：裁剪后的目标字节大小（0=清空，可选，默认0）"
                    },
                    "mode_bits": {
                        "type": "string",
                        "description": "Create 操作时的权限位，如 '0644'、'0755'（可选，默认 '0644'）"
                    }
                },
                "required": ["action"]
            }
        },
        "display": {
            "name_cn": "文件操作",
            "description_cn": "创建、删除、复制、读取、写入、打开、关闭、重命名、截断文件",
            "icon": "fa-file-alt"
        }
    }
]


def _resolve_path(path: str) -> str:
    """解析路径为绝对路径"""
    if not path:
        return ""
    return os.path.abspath(path)


def _format_metadata(filepath: str) -> str:
    """获取文件元数据字符串"""
    try:
        st = os.stat(filepath)
        perms = oct(stat.S_IMODE(st.st_mode))
        size = st.st_size
        from datetime import datetime
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        ctime = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        return f"权限={perms}, 大小={size}B, 修改时间={mtime}, 创建时间={ctime}"
    except Exception as e:
        return f"获取元数据失败: {e}"


def _do_create(path: str, content: str = "", mode_bits: str = "0644") -> str:
    """创建新文件，写入内容，设置初始元数据"""
    if not path:
        return "❌ 请提供文件路径"

    abs_path = _resolve_path(path)

    if os.path.exists(abs_path):
        return f"⚠️ 文件已存在: {abs_path}（不会覆盖已有文件）"

    try:
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        try:
            bits = int(mode_bits, 8) if mode_bits else 0o644
            os.chmod(abs_path, stat.S_IMODE(bits))
        except Exception:
            pass

        meta = _format_metadata(abs_path)
        size_info = f" ({len(content)} 字节)" if content else " (空文件)"
        return f"✅ 已创建文件: {abs_path}{size_info}\n📋 元数据: {meta}"

    except PermissionError:
        return f"❌ 无权限创建文件: {abs_path}"
    except Exception as e:
        return f"❌ 创建失败: {e}"


def _do_delete(path: str) -> str:
    """删除文件，释放磁盘空间"""
    if not path:
        return "❌ 请提供文件路径"

    abs_path = _resolve_path(path)

    if not os.path.exists(abs_path):
        return f"❌ 路径不存在: {abs_path}"

    try:
        if os.path.isfile(abs_path):
            size = os.path.getsize(abs_path)
            os.remove(abs_path)
            return f"✅ 已删除文件: {abs_path}（释放 {size} 字节空间）"
        elif os.path.isdir(abs_path):
            try:
                os.rmdir(abs_path)
                return f"✅ 已删除空目录: {abs_path}"
            except OSError:
                return f"❌ 目录非空，请使用 directory_ops(action=Rmdir, recursive=true) 删除目录"
        else:
            return f"❌ 路径不是常规文件: {abs_path}"
    except PermissionError:
        return f"❌ 无权限删除: {abs_path}"
    except Exception as e:
        return f"❌ 删除失败: {e}"


def _do_copy(source: str, dest: str) -> str:
    """复制文件或目录到目标位置"""
    if not source or not dest:
        return "❌ 请提供源路径(source)和目标路径(dest)"

    abs_source = _resolve_path(source)
    abs_dest = _resolve_path(dest)

    if not os.path.exists(abs_source):
        return f"❌ 源路径不存在: {abs_source}"

    try:
        if os.path.isdir(abs_source):
            shutil.copytree(abs_source, abs_dest, dirs_exist_ok=True)
            return f"✅ 已复制目录:\n   源: {abs_source}\n   目标: {abs_dest}"
        else:
            parent = os.path.dirname(abs_dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(abs_source, abs_dest)
            return f"✅ 已复制文件:\n   源: {abs_source}\n   目标: {abs_dest}"
    except Exception as e:
        return f"❌ 复制失败: {e}"


def _do_read(path: str, offset: int = 0, length: int = 0) -> str:
    """读取指定文件的内容，支持偏移和长度"""
    if not path:
        return "❌ 请提供文件路径"

    abs_path = _resolve_path(path)

    if not os.path.exists(abs_path):
        return f"❌ 文件不存在: {abs_path}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            if offset > 0:
                f.seek(offset)
            if length > 0:
                content = f.read(length)
            else:
                content = f.read()
        size = len(content)
        meta = _format_metadata(abs_path)
        lines = content.count("\n") + 1
        preview = content[:200] + ("..." if len(content) > 200 else "")
        return (f"📄 {abs_path} ({size} 字符, {lines} 行)\n"
                f"📋 元数据: {meta}\n"
                f"--- 内容预览 (前 {min(size, 200)} 字符) ---\n{preview}")
    except FileNotFoundError:
        return f"❌ 文件未找到: {abs_path}"
    except Exception as e:
        return f"❌ 读取失败: {e}"


def _do_write(path: str, content: str = "", offset: int = -1) -> str:
    """写入内容到指定文件，支持指定偏移位置"""
    if not path:
        return "❌ 请提供文件路径"

    abs_path = _resolve_path(path)

    try:
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if offset >= 0:
            # 在指定偏移处写入
            if not os.path.exists(abs_path):
                return f"❌ 文件不存在（偏移写入需要已有文件）: {abs_path}"
            with open(abs_path, "r+", encoding="utf-8") as f:
                f.seek(offset)
                f.write(content)
            return f"✅ 已写入 {abs_path}（偏移 {offset} 处写入 {len(content)} 字符）"
        else:
            # 覆盖写入
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"✅ 已写入 {abs_path}（{len(content)} 字符）"
    except FileNotFoundError:
        return f"❌ 文件未找到: {abs_path}"
    except Exception as e:
        return f"❌ 写入失败: {e}"


def _do_open(path: str, mode: str = "r") -> str:
    """打开文件，建立 FCB，返回文件描述符"""
    global _next_fd, _open_fds
    if not path:
        return "❌ 请提供文件路径"

    abs_path = _resolve_path(path)

    if not os.path.exists(abs_path):
        return f"❌ 文件不存在: {abs_path}"

    if mode not in ("r", "w", "a"):
        return "❌ mode 参数必须为 r（只读）、w（写入）或 a（追加）"

    try:
        f = open(abs_path, mode, encoding="utf-8")
        fd = _next_fd
        _next_fd += 1

        _open_fds[fd] = {
            "path": abs_path,
            "mode": mode,
            "opened_at": time.time(),
            "file": f,
        }

        meta = _format_metadata(abs_path)
        return (f"✅ 已打开文件 (fd={fd}): {abs_path}\n"
                f"📋 模式: {'只读' if mode == 'r' else '写入' if mode == 'w' else '追加'}\n"
                f"📋 元数据: {meta}")
    except Exception as e:
        return f"❌ 打开失败: {e}"


def _do_close(fd: int = None) -> str:
    """关闭文件描述符，刷入缓冲"""
    global _open_fds

    if fd is None:
        if not _open_fds:
            return "📋 当前没有打开的文件描述符"
        lines = ["📋 当前打开的文件描述符："]
        for fdid, info in _open_fds.items():
            from datetime import datetime
            opened = datetime.fromtimestamp(info["opened_at"]).strftime("%H:%M:%S")
            lines.append(f"  fd={fdid}  {info['path']}  ({info['mode']})  [{opened}]")
        return "\n".join(lines)

    if fd not in _open_fds:
        valid = sorted(_open_fds.keys())
        return f"❌ 无效的 fd={fd}，当前打开的 fd: {valid if valid else '无'}"

    try:
        info = _open_fds[fd]
        f = info["file"]
        path = info["path"]
        f.close()
        del _open_fds[fd]
        return f"✅ 已关闭 fd={fd}: {path}（缓冲数据已刷入磁盘）"
    except Exception as e:
        return f"❌ 关闭 fd={fd} 失败: {e}"


def _do_rename(path: str, new_path: str) -> str:
    """修改文件路径名"""
    if not path:
        return "❌ 请提供原文件路径"
    if not new_path:
        return "❌ 请提供新文件路径（new_path 参数）"

    abs_path = _resolve_path(path)
    abs_new = _resolve_path(new_path)

    if not os.path.exists(abs_path):
        return f"❌ 原文件不存在: {abs_path}"

    if os.path.exists(abs_new):
        return f"❌ 目标路径已存在: {abs_new}（不会覆盖）"

    try:
        parent = os.path.dirname(abs_new)
        if parent:
            os.makedirs(parent, exist_ok=True)

        os.rename(abs_path, abs_new)
        return f"✅ 已重命名:\n   原路径: {abs_path}\n   新路径: {abs_new}"
    except Exception as e:
        return f"❌ 重命名失败: {e}"


def _do_truncate(path: str, size: int = 0) -> str:
    """截断文件到指定大小"""
    if not path:
        return "❌ 请提供文件路径"

    abs_path = _resolve_path(path)

    if not os.path.exists(abs_path):
        return f"❌ 文件不存在: {abs_path}"

    if not os.path.isfile(abs_path):
        return f"❌ 路径不是常规文件: {abs_path}"

    try:
        original_size = os.path.getsize(abs_path)
        with open(abs_path, "r+b") as f:
            f.truncate(size)

        if size == 0:
            return f"✅ 已清空文件: {abs_path}（原大小 {original_size} 字节 → 0 字节）"
        elif size < original_size:
            return (f"✅ 已裁剪文件: {abs_path}\n"
                    f"   原大小: {original_size} 字节 → {size} 字节（裁剪了 {original_size - size} 字节）")
        elif size > original_size:
            return (f"✅ 已扩展文件: {abs_path}\n"
                    f"   原大小: {original_size} 字节 → {size} 字节（扩展了 {size - original_size} 字节）")
        else:
            return f"✅ 文件大小未变: {abs_path}（{size} 字节）"
    except Exception as e:
        return f"❌ 截断失败: {e}"


def file_ops(arguments: dict) -> str:
    """文件操作统一入口

    @param arguments: dict - 包含 action 及其他参数
        - action: str - 操作类型 (Create/Delete/Copy/Read/Write/Open/Close/Rename/Truncate)
        - path: str - 文件路径
        - source: str (Copy) - 源路径
        - dest: str (Copy) - 目标路径
        - new_path: str (Rename) - 新路径
        - content: str (Create/Write) - 文件内容
        - offset: int (Read/Write) - 字节偏移
        - length: int (Read) - 读取长度
        - mode: str (Open) - 打开模式 r/w/a
        - fd: int (Close) - 文件描述符编号
        - size: int (Truncate) - 目标大小
        - mode_bits: str (Create) - 权限位
    @return str - 操作结果
    """
    if isinstance(arguments, str):
        import json
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return "❌ 参数格式错误，需要 JSON 对象"

    action = arguments.get("action", "").strip()
    path = arguments.get("path", "").strip()
    source = arguments.get("source", "").strip()
    dest = arguments.get("dest", "").strip()
    new_path = arguments.get("new_path", "").strip()
    content = arguments.get("content", "")
    offset = arguments.get("offset", 0)
    length = arguments.get("length", 0)
    mode = arguments.get("mode", "r").strip()
    fd = arguments.get("fd", None)
    size = arguments.get("size", 0)
    mode_bits = arguments.get("mode_bits", "0644").strip()

    if not action:
        return "❌ 请提供 action 参数"

    if action == "Create":
        return _do_create(path, content, mode_bits)
    elif action == "Delete":
        return _do_delete(path)
    elif action == "Copy":
        return _do_copy(source, dest)
    elif action == "Read":
        return _do_read(path, offset, length)
    elif action == "Write":
        return _do_write(path, content, offset)
    elif action == "Open":
        return _do_open(path, mode)
    elif action == "Close":
        return _do_close(fd)
    elif action == "Rename":
        return _do_rename(path, new_path)
    elif action == "Truncate":
        return _do_truncate(path, size)
    else:
        return f"❌ 未知操作: {action}，支持的操作为 Create/Delete/Copy/Read/Write/Open/Close/Rename/Truncate"


# ==========================================
# 在模块卸载时自动关闭所有打开的 fd
# ==========================================
import atexit


@atexit.register
def _cleanup_open_fds():
    """程序退出时关闭所有打开的文件描述符"""
    global _open_fds
    for fd, info in list(_open_fds.items()):
        try:
            info["file"].close()
        except Exception:
            pass
    _open_fds.clear()