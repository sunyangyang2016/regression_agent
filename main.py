"""
App Agent · 主入口
GUI 模式：python main.py
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置 stdout 编码为 UTF-8（防止 Windows 控制台 emoji 崩溃）
os.environ["PYTHONIOENCODING"] = "utf-8"

# 将 Windows 终端代码页切换为 UTF-8，防止 Chromium 控制台日志中文乱码
if sys.platform == "win32":
    os.system("chcp 65001 > NUL")

# ★ 必须在 QApplication 创建之前设置此属性 + 导入 QtWebEngineWidgets
from PyQt5.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PyQt5 import QtWebEngineWidgets  # noqa: F401

# 捕获 C 级崩溃（segfault/SIGABRT 等）
import faulthandler
faulthandler.enable()

# 启用 Chromium 渲染进程日志
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-logging --v=0"


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