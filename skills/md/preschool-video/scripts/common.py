# -*- coding: utf-8 -*-
"""
preschool-video 脚本公共工具：项目根路径解析 + 前端命令 HTTP 通知。

供同目录下 video_search.py / video_control.py / video_catcher_runner.py 共用，
消除三处重复的 ROOT 引导与 send_command 实现。
"""
import json
import os
import sys
import urllib.request

# Windows 控制台默认 GBK，emoji/中文打印会触发 UnicodeEncodeError，
# 统一把 stdout/stderr 切到 UTF-8（不影响 Qt 进程内导入，仅对流对象做 reconfigure）。
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream and _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def project_root():
    """项目根目录（scripts → preschool-video → md → skills → 根目录，共 5 级）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    ))))


# 端口发现文件（video_plugin 的 VideoObserver 启动时写入命令端点端口）
PORT_FILE = os.path.join(project_root(), "storage", "video_plugin.json")


def _get_command_endpoint() -> str:
    """读取 video_plugin 的 HTTP 命令端点；不可用时返回空串"""
    try:
        if not os.path.exists(PORT_FILE):
            return ""
        with open(PORT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        port = data.get("port")
        if not port:
            return ""
        return f"http://127.0.0.1:{port}/video_command"
    except Exception:
        return ""


def send_command(payload: dict) -> bool:
    """POST 命令到 video_plugin 的 HTTP 命令端点 → PluginBus 事件控制/刷新前端

    返回 True 表示已送达主进程；False 表示应用未运行或插件未加载。
    """
    endpoint = _get_command_endpoint()
    if not endpoint:
        print("⚠️ 无法定位视频插件命令端点（应用未运行或 video_plugin 未加载）")
        return False
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"⚠️ 命令送达失败（应用未运行？）：{e}")
        return False


if __name__ == "__main__":
    print("PROJECT_ROOT:", project_root())
    print("PORT_FILE:", PORT_FILE)
    print("ENDPOINT:", _get_command_endpoint() or "(未找到，应用未运行？)")
