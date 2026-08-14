"""
Agent - 应用主入口
"""
import sys
import os
import json
import time
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, QCoreApplication
from PyQt5.QtWidgets import QApplication, QMainWindow, QDesktopWidget
from PyQt5.QtGui import QIcon

from core.event_bus import EventBus
from config.model_config import ModelConfig
from ai.client import AIClient

LOG = "[Agent]"


class Agent:
    """Agent 应用主类"""

    def __init__(self):
        self.bus = EventBus()
        self.model_config = ModelConfig()
        self.ai_client = AIClient(self.model_config)
        self.app_controller = None
        self._initialized = False

        try:
            import faulthandler
            faulthandler.disable()
        except Exception:
            pass

    def run(self):
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        try:
            # 应用图标（resources/app_icon.ico，⚡ 闪电品牌，与主界面 logo 一致）
            _icon_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "resources", "app_icon.ico",
            )
            if os.path.exists(_icon_path):
                app.setWindowIcon(QIcon(_icon_path))
        except Exception:
            pass

        from controller.app_controller import AppController
        self.app_controller = AppController(
            model_config=self.model_config,
            ai_client=self.ai_client
        )

        window = self.app_controller.start()
        app.aboutToQuit.connect(self.cleanup)

        result = app.exec_()
        sys.exit(result)

    def cleanup(self):
        print(f"{LOG} 🧹 开始清理资源...")
        if self.app_controller:
            try:
                self.app_controller.cleanup()
            except Exception:
                pass
        print(f"{LOG} ✅ 清理完成")


def create_default_app():
    return Agent()


if __name__ == "__main__":
    app = create_default_app()
    sys.exit(app.run())