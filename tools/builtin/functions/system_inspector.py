"""
system_inspector - 工具

可直接调用:
    system_inspector(args) -> str
"""
import json, os, shutil, re, random, string as str_mod, platform

# ===== 工具定义 =====
TOOLS = [
    {
            "name": "system_inspector",
            "description": "系统信息查询：CPU占用、内存使用、磁盘使用、操作系统信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_type": {"type": "string", "description": "类型: summary(全部), cpu, memory, disk, os, python, env"}
                }
            ,
        "display": {"name_cn": "系统信息", "description_cn": "查询CPU/内存/磁盘/系统信息", "icon": "fa-tachometer-alt"}}
        ,
        "display": {"name_cn": "系统信息", "description_cn": "查询CPU/内存/磁盘/系统信息", "icon": "fa-tachometer-alt"}},
]

def system_inspector(args):
    """系统信息查询 — 可直接调用
    
    @param args: dict - {"info_type": "summary(全部)|cpu|memory|disk|os|python|env"}
    @return str - 系统信息

    调用示例:
        system_inspector({"info_type": "summary"})
        system_inspector({"info_type": "cpu"})
        system_inspector({"info_type": "memory"})
    """
    if isinstance(args, str):
        return system_inspector({"info_type": args})
    if isinstance(args, dict):
        info_type = args.get("info_type", "summary")
    else:
        info_type = "summary"
    try:
        # 尝试导入 psutil（内存在 summary 中默认不装 psutil 也可用）
        try:
            import psutil
            _has_psutil = True
        except ImportError:
            _has_psutil = False

        if info_type == "os":
            return f"系统: {platform.system()} {platform.release()}"
        elif info_type == "python":
            return f"Python {platform.python_version()} ({platform.architecture()[0]})"
        elif info_type == "cpu":
            if not _has_psutil:
                return "CPU 信息需安装 psutil (pip install psutil)"
            return (
                f"CPU 占用: {psutil.cpu_percent(interval=0.1)}%\n"
                f"CPU 核心数: {psutil.cpu_count(logical=True)} (逻辑) / {psutil.cpu_count(logical=False)} (物理)\n"
                f"CPU 频率: {psutil.cpu_freq().current:.0f} MHz"
            )
        elif info_type == "memory":
            if not _has_psutil:
                return "内存信息需安装 psutil (pip install psutil)"
            mem = psutil.virtual_memory()
            return (
                f"总内存: {mem.total // 1024 ** 3}GB\n"
                f"已用: {mem.percent}% ({mem.used // 1024 ** 3}GB)\n"
                f"可用: {mem.available // 1024 ** 3}GB"
            )
        elif info_type == "disk":
            if not _has_psutil:
                return "磁盘信息需安装 psutil (pip install psutil)"
            disk = psutil.disk_usage('/')
            return (
                f"总空间: {disk.total // 1024 ** 3}GB\n"
                f"已用: {disk.percent}% ({disk.used // 1024 ** 3}GB)\n"
                f"可用: {disk.free // 1024 ** 3}GB"
            )
        elif info_type == "summary":
            result = [
                f"系统: {platform.system()} {platform.release()}",
                f"Python: {platform.python_version()} ({platform.architecture()[0]})"
            ]
            if _has_psutil:
                result.append(f"CPU: {psutil.cpu_percent(interval=0.1)}% ({psutil.cpu_count()} 核)")
                mem = psutil.virtual_memory()
                result.append(f"内存: {mem.percent}% ({mem.used // 1024 ** 3}GB/{mem.total // 1024 ** 3}GB)")
                disk = psutil.disk_usage('/')
                result.append(f"磁盘: {disk.percent}% ({disk.used // 1024 ** 3}GB/{disk.total // 1024 ** 3}GB)")
            else:
                result.append("内存/磁盘/CPU: 需安装 psutil (pip install psutil)")
            return "\n".join(result)
        elif info_type == "env":
            return f"当前目录: {os.getcwd()}\n用户: {os.environ.get('USERNAME', 'unknown')}"
        return f"未知类型: {info_type}"
    except Exception as e:
        return f"查询失败: {e}"

