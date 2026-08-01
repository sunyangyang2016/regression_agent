"""
插件基类 - UI 插件和业务插件的抽象定义
所有插件模块继承此类，实现统一的注册/生命周期管理
"""
from typing import Optional
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QWidget


class UIPlugin(QObject):
    """UI 插件基类 - 所有 UI 面板继承此类"""
    
    # 插件元数据 - 子类重写
    plugin_id: str = "base"
    plugin_name: str = "基础插件"
    icon: str = "📦"
    position: str = "sidebar"  # sidebar | center | header | footer | modal
    priority: int = 100        # 排序优先级（越小越靠前）
    
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._widget: Optional[QWidget] = None
        self._bridges: list = []  # QWebChannel 注册对象列表
    
    def create_widget(self) -> Optional[QWidget]:
        """创建 UI 组件（如果需要 PyQt 原生控件）"""
        return None
    
    def get_html_content(self) -> Optional[str]:
        """获取 HTML 模板片段（返回字符串或 None）"""
        return None
    
    def get_js_file(self) -> Optional[str]:
        """获取 JS 文件路径"""
        return None
    
    def get_bridge_objects(self) -> list:
        """获取需要注册到 QWebChannel 的对象列表
        Returns: [(name, QObject), ...]
        """
        return []
    
    def on_register(self):
        """插件注册到主窗口时调用"""
        pass
    
    def on_unregister(self):
        """插件从主窗口卸载时调用"""
        pass
    
    def on_theme_change(self, theme_name: str):
        """主题变更时调用"""
        pass


class BusinessPlugin:
    """业务插件基类 - 所有业务模块继承此类"""
    
    plugin_id: str = "base_business"
    plugin_name: str = "基础业务"
    
    def __init__(self):
        self._initialized = False
    
    def initialize(self):
        """初始化（连接事件总线）"""
        self._initialized = True
    
    def cleanup(self):
        """清理资源"""
        self._initialized = False
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized