"""监控插件控制器层 - 组装监控数据供桥接层调用"""
from ..model import monitor_model


def get_stats() -> dict:
    """获取系统汇总统计（CPU/内存/磁盘 I/O/网络）"""
    try:
        return {
            "cpu": monitor_model.get_cpu_info(),
            "memory": monitor_model.get_memory_info(),
            "disk_io": monitor_model.get_disk_io(),
            "network": monitor_model.get_network_info(),
            "load": monitor_model.get_load_average(),
            "uptime": monitor_model._format_uptime(monitor_model.get_boot_time()),
        }
    except Exception as e:
        print(f"[MonitorController] [ERROR] get_stats: {e}")
        return {
            "cpu": {"percent": 0, "freq": "0 GHz", "cores": 1},
            "memory": {"total": 0, "used": 0, "percent": 0},
            "disk_io": {"read_mb": 0, "write_mb": 0, "total_mb": 0},
            "network": {"rx": "0 B/s", "tx": "0 B/s", "conns": 0},
            "load": [0.0, 0.0, 0.0],
            "uptime": "0d 0h",
        }


def get_processes(max_count: int = 8) -> list:
    """获取 Top N 进程详情"""
    try:
        return monitor_model.get_processes(max_count)
    except Exception as e:
        print(f"[MonitorController] [ERROR] get_processes: {e}")
        return []


def get_disks() -> list:
    """获取磁盘分区使用情况"""
    try:
        return monitor_model.get_disk_usage()
    except Exception as e:
        print(f"[MonitorController] [ERROR] get_disks: {e}")
        return []


def get_all(max_processes: int = 8) -> dict:
    """一次性获取全部监控数据"""
    try:
        return monitor_model.collect_all(max_processes)
    except Exception as e:
        print(f"[MonitorController] [ERROR] get_all: {e}")
        return {}