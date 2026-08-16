"""
App Agent · 主入口
GUI 模式：python main.py
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# RAG MCP 服务器已独立到 tools/mcp/server/rag-mcp-server/（rag_mcp_server 包）。
# 应用进程（RAG 导入插件）从这里导入该包。
sys.path.insert(1, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tools", "mcp", "server", "rag-mcp-server"))

# 修复 stdout/stderr 编码为 UTF-8（防止 Windows 控制台 emoji 崩溃）
# 注意：PYTHONIOENCODING 环境变量必须在解释器启动前设置才生效，
# 运行时设置无效。必须直接调用 reconfigure 重设标准流编码。
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ["PYTHONIOENCODING"] = "utf-8"

# 将 Windows 终端代码页切换为 UTF-8，防止 Chromium 控制台日志中文乱码
if sys.platform == "win32":
    os.system("chcp 65001 > NUL")

# ★ 预载系统 MSVC 运行库（必须在导入 QtWebEngine 之前）。
#   QtWebEngine 自带的 Qt5/bin/ 里有旧版 msvcp140/vcruntime140，导入时会把该目录
#   加入 DLL 搜索路径，导致之后 onnxruntime 的 onnxruntime_pybind11_state.pyd
#   绑定到旧运行库而加载失败（DLL load failed ... 初始化例程失败）。
#   先把系统运行库载入进程，Windows 会按名复用已加载的版本，Qt 与 onnxruntime 均用系统版。
if sys.platform == "win32":
    import ctypes
    _system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    for _dll in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
        try:
            ctypes.windll.kernel32.LoadLibraryW(os.path.join(_system32, _dll))
        except Exception:
            pass  # 系统缺该运行库时静默，保持原有行为

# ★ 必须在 QApplication 创建之前设置此属性 + 导入 QtWebEngineWidgets
from PyQt5.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PyQt5 import QtWebEngineWidgets  # noqa: F401

# 捕获 C 级崩溃（segfault/SIGABRT 等）
import faulthandler
faulthandler.enable()

# 启用 Chromium 渲染进程日志 + 允许自动播放/远程媒体访问（视频中心需要）
# ★ 2026-08 实测：PyQt5 5.15.2 官方 wheel 的 QtWebEngine 因专利授权编译期禁用
#   H.264/AAC/HEVC 解码器（canPlayType 全部为空），Chromium flags 无法开启。
#   PlatformHEVCDecoderSupport* 仅对"已内置 HEVC 解码器"的构建有效，保留备用。
#   实际播放由 video_plugin/player.py 智能处理：原生支持(VP8/VP9/Opus)直接播，
#   H.264/AAC/HEVC 自动 ffmpeg 实时转码为 VP8/Opus WebM。
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--enable-logging --v=0 "
    "--autoplay-policy=no-user-gesture-required "
    "--allow-running-insecure-content "
    "--enable-features=ProprietaryCodecs,PlatformHEVCDecoderSupport,PlatformHEVCDecoderSupport2"
)


def _global_excepthook(exc_type, exc_value, exc_tb):
    """全局未捕获异常处理器"""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "crash.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    now = __import__('datetime').datetime.now().isoformat()
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\nCRASH TIME: {now}\n{'='*60}\n{msg}\n{'='*60}\n")
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"💥 Python 异常！查看 logs/crash.log 获取详情", file=sys.stderr)
    print(msg, file=sys.stderr)


sys.excepthook = _global_excepthook


def main():
    try:
        # ★ 数据库全局初始化（在任何组件创建前）
        # 集中封装：建连接 + 注入模型 + 确保 4 张表存在（幂等建表，不做数据迁移）
        from storage.initializer import DatabaseInitializer
        DatabaseInitializer.initialize()

        from core.agent import Agent
        agent = Agent()
        agent.run()
    except Exception:
        _global_excepthook(*sys.exc_info())


if __name__ == "__main__":
    main()