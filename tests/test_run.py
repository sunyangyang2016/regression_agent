"""测试运行脚本"""
import sys
import os

# 添加项目根目录到 sys.path（tests/ 的父目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在 QApplication 创建之前设置
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# 设置 Qt WebEngine 属性
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

from window.ui_main import RegressionAgentApp

print("✅ 所有模块导入成功")

# 测试创建应用
app = QApplication(sys.argv)
print("✅ QApplication 创建成功")

# 测试创建主窗口
window = RegressionAgentApp()
print("✅ RegressionAgentApp 创建成功")
print(f"   窗口大小: {window.width()}x{window.height()}")
print(f"   窗口标题: {window.windowTitle()}")
print(f"   最小尺寸: {window.minimumWidth()}x{window.minimumHeight()}")

print("\n🎉 所有测试通过！")