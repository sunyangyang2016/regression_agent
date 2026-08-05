"""监控插件模型层 - 采集真实系统数据"""
import os
import time

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _format_bytes(num):
    """将字节数格式化为人类可读字符串"""
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "0B"
    for unit in ["B", "K", "M", "G", "T"]:
        if abs(num) < 1024.0 or unit == "T":
            return f"{num:.0f}{unit}" if unit == "B" else f"{num:.1f}{unit}"
        num /= 1024.0
    return "0B"


def _format_speed(bps):
    """将字节/秒格式化为速率字符串"""
    try:
        bps = float(bps)
    except (TypeError, ValueError):
        return "0 B/s"
    if bps >= 1024 ** 3:
        return f"{bps / 1024 ** 3:.2f} Gbps"
    if bps >= 1024 ** 2:
        return f"{bps / 1024 ** 2:.1f} Mbps"
    if bps >= 1024:
        return f"{bps / 1024:.1f} KB/s"
    return f"{bps:.0f} B/s"


def _format_freq(hz):
    """将 Hz 格式化为 GHz/MHz"""
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return "0 GHz"
    if hz >= 1024 ** 3:
        return f"{hz / 1024 ** 3:.1f} GHz"
    if hz >= 1024 ** 2:
        return f"{hz / 1024 ** 2:.0f} MHz"
    return f"{hz:.0f} Hz"


# ──────────────────────────────────────────────
# 数据采集
# ──────────────────────────────────────────────


def get_cpu_info():
    """CPU 使用率 / 频率 / 核心数"""
    if not PSUTIL_AVAILABLE:
        return {"percent": 0, "freq": "0 GHz", "cores": os.cpu_count() or 1}
    try:
        percent = psutil.cpu_percent(interval=None)
        freq = psutil.cpu_freq()
        freq_hz = freq.current * 1024 ** 2 if freq else 0  # MHz -> Hz
        return {
            "percent": round(percent, 1),
            "freq": _format_freq(freq_hz),
            "cores": psutil.cpu_count(logical=True) or os.cpu_count() or 1,
        }
    except Exception:
        return {"percent": 0, "freq": "0 GHz", "cores": os.cpu_count() or 1}


def get_memory_info():
    """物理内存 总量/已用/使用率"""
    if not PSUTIL_AVAILABLE:
        return {"total": 0, "used": 0, "percent": 0}
    try:
        vm = psutil.virtual_memory()
        return {
            "total": vm.total,
            "used": vm.used,
            "percent": round(vm.percent, 1),
        }
    except Exception:
        return {"total": 0, "used": 0, "percent": 0}


def get_disk_usage():
    """磁盘分区使用情况"""
    if not PSUTIL_AVAILABLE:
        return []
    try:
        parts = []
        for part in psutil.disk_partitions(all=False):
            if part.fstype in ("", None):
                continue
            # 跳过 Windows 系统保留分区
            if os.name == "nt" and part.fstype.lower() in ("recovery", "system"):
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                parts.append({
                    "mount": part.mountpoint,
                    "device": part.device,
                    "total": usage.total,
                    "used": usage.used,
                    "percent": round(usage.percent, 1),
                })
            except (PermissionError, OSError):
                continue
        return parts
    except Exception:
        return []


def get_disk_io():
    """磁盘读写速率 (MB/s)"""
    if not PSUTIL_AVAILABLE:
        return {"read_mb": 0, "write_mb": 0, "total_mb": 0, "readable": "0 MB/s", "writable": "0 MB/s"}
    try:
        io1 = psutil.disk_io_counters()
        if not io1:
            return {"read_mb": 0, "write_mb": 0, "total_mb": 0, "readable": "0 MB/s", "writable": "0 MB/s"}
        time.sleep(0.3)
        io2 = psutil.disk_io_counters()
        if not io2:
            return {"read_mb": 0, "write_mb": 0, "total_mb": 0, "readable": "0 MB/s", "writable": "0 MB/s"}
        dt = 0.3
        read_bps = (io2.read_bytes - io1.read_bytes) / dt
        write_bps = (io2.write_bytes - io1.write_bytes) / dt
        return {
            "read_mb": round(read_bps / 1024 / 1024, 1),
            "write_mb": round(write_bps / 1024 / 1024, 1),
            "total_mb": round((read_bps + write_bps) / 1024 / 1024, 1),
            "readable": _format_speed(read_bps),
            "writable": _format_speed(write_bps),
        }
    except Exception:
        return {"read_mb": 0, "write_mb": 0, "total_mb": 0, "readable": "0 MB/s", "writable": "0 MB/s"}


def get_network_info():
    """网络收发速率 + 连接数"""
    if not PSUTIL_AVAILABLE:
        return {"rx_bps": 0, "tx_bps": 0, "rx": "0 B/s", "tx": "0 B/s", "conns": 0}
    try:
        net1 = psutil.net_io_counters()
        if not net1:
            return {"rx_bps": 0, "tx_bps": 0, "rx": "0 B/s", "tx": "0 B/s", "conns": 0}
        time.sleep(0.3)
        net2 = psutil.net_io_counters()
        if not net2:
            return {"rx_bps": 0, "tx_bps": 0, "rx": "0 B/s", "tx": "0 B/s", "conns": 0}
        dt = 0.3
        rx_bps = (net2.bytes_recv - net1.bytes_recv) / dt
        tx_bps = (net2.bytes_sent - net1.bytes_sent) / dt
        try:
            conns = len(psutil.net_connections(kind="inet"))
        except Exception:
            conns = 0
        rx_mbps = rx_bps * 8 / 1024 / 1024
        tx_mbps = tx_bps * 8 / 1024 / 1024
        return {
            "rx_bps": round(rx_bps, 2),
            "tx_bps": round(tx_bps, 2),
            "rx": _format_speed(rx_bps),
            "tx": _format_speed(tx_bps),
            "rx_mbps": round(rx_mbps, 1),
            "tx_mbps": round(tx_mbps, 1),
            "conns": conns,
        }
    except Exception:
        return {"rx_bps": 0, "tx_bps": 0, "rx": "0 B/s", "tx": "0 B/s", "conns": 0}


def get_load_average():
    """负载均衡 (1/5/15 分钟)"""
    if not PSUTIL_AVAILABLE:
        return [0.0, 0.0, 0.0]
    try:
        if hasattr(psutil, "getloadavg"):
            return [round(x, 2) for x in psutil.getloadavg()]
    except Exception:
        pass
    return [0.0, 0.0, 0.0]


def get_boot_time():
    """系统运行时长 (秒)"""
    if not PSUTIL_AVAILABLE:
        return 0
    try:
        return int(time.time() - psutil.boot_time())
    except Exception:
        return 0


def _format_uptime(seconds):
    """格式化运行时长"""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "0d 0h"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def get_processes(max_count=8):
    """按 CPU 使用率排序获取 Top N 进程"""
    if not PSUTIL_AVAILABLE:
        return []
    try:
        procs = []
        for p in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "memory_info", "num_threads"]
        ):
            try:
                pinfo = p.info
                mem_info = pinfo.get("memory_info") or {}
                rss = mem_info.rss if hasattr(mem_info, "rss") else (mem_info.get("rss") if isinstance(mem_info, dict) else 0)
                vms = mem_info.vms if hasattr(mem_info, "vms") else (mem_info.get("vms") if isinstance(mem_info, dict) else 0)
                procs.append({
                    "pid": pinfo.get("pid") or 0,
                    "name": pinfo.get("name") or "unknown",
                    "cpu_percent": round(pinfo.get("cpu_percent") or 0, 1),
                    "mem_percent": round(pinfo.get("memory_percent") or 0, 1),
                    "rss": rss,
                    "vsz": vms,
                    "threads": pinfo.get("num_threads") or 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        # 按 CPU 使用率排序取前 N
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return procs[:max_count]
    except Exception:
        return []


def collect_all(max_processes=8):
    """一次性采集全部监控数据"""
    cpu = get_cpu_info()
    mem = get_memory_info()
    disk_usage = get_disk_usage()
    disk_io = get_disk_io()
    net = get_network_info()
    load = get_load_average()
    uptime = get_boot_time()
    procs = get_processes(max_processes)

    # 汇总
    total_cpu = round(sum(p["cpu_percent"] for p in procs), 1)
    total_mem = round(sum(p["mem_percent"] for p in procs), 1)
    total_rss = sum(p["rss"] for p in procs)
    total_threads = sum(p["threads"] for p in procs)

    return {
        "hostname": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "localhost"),
        "os": os.name,
        "cpu": cpu,
        "memory": mem,
        "disk_io": disk_io,
        "network": net,
        "load": load,
        "uptime": _format_uptime(uptime),
        "processes": procs,
        "disks": disk_usage,
        "summary": {
            "cpu_total": total_cpu,
            "mem_total": total_mem,
            "rss_total": total_rss,
            "rss_total_str": _format_bytes(total_rss),
            "threads_total": total_threads,
        },
    }