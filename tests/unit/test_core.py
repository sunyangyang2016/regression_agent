"""核心模块单元测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestEventBus:
    """事件总线测试"""

    def test_import(self):
        """测试事件总线可导入"""
        from core.event_bus import EventBus
        assert EventBus is not None

    def test_singleton(self):
        """测试单例模式"""
        from core.event_bus import EventBus
        bus1 = EventBus()
        bus2 = EventBus()
        assert bus1 is bus2

    def test_emit_and_listen(self):
        """测试事件发布与监听"""
        from core.event_bus import EventBus
        bus = EventBus()
        results = []

        @bus.on("test_event")
        def handler(data):
            results.append(data)

        bus.emit("test_event", {"msg": "hello"})
        assert len(results) == 1
        assert results[0]["msg"] == "hello"

    def test_off(self):
        """测试取消监听"""
        from core.event_bus import EventBus
        bus = EventBus()
        results = []

        @bus.on("test_event")
        def handler(data):
            results.append(data)

        bus.off("test_event", handler)
        bus.emit("test_event", {"msg": "hello"})
        assert len(results) == 0


class TestConstants:
    """常量测试"""

    def test_import(self):
        """测试常量可导入"""
        from core.constants import APP_NAME, APP_VERSION
        assert APP_NAME is not None
        assert APP_VERSION is not None

    def test_app_info(self):
        """测试应用信息"""
        from core.constants import APP_NAME, APP_VERSION
        assert isinstance(APP_NAME, str)
        assert isinstance(APP_VERSION, str)
        assert len(APP_NAME) > 0
        assert len(APP_VERSION) > 0


class TestStateManager:
    """状态管理器测试"""

    def test_import(self):
        """测试状态管理器可导入"""
        from core.state_manager import StateManager
        assert StateManager is not None

    def test_set_and_get(self):
        """测试设置和获取状态"""
        from core.state_manager import StateManager
        sm = StateManager()
        sm.set("test_key", "test_value")
        assert sm.get("test_key") == "test_value"

    def test_get_default(self):
        """测试获取默认值"""
        from core.state_manager import StateManager
        sm = StateManager()
        assert sm.get("nonexistent", "default") == "default"

    def test_has_key(self):
        """测试检查键是否存在"""
        from core.state_manager import StateManager
        sm = StateManager()
        sm.set("key1", "value1")
        assert sm.has("key1") is True
        assert sm.has("key2") is False

    def test_delete(self):
        """测试删除状态"""
        from core.state_manager import StateManager
        sm = StateManager()
        sm.set("key", "value")
        sm.delete("key")
        assert sm.has("key") is False

    def test_clear(self):
        """测试清空状态"""
        from core.state_manager import StateManager
        sm = StateManager()
        sm.set("key1", "value1")
        sm.set("key2", "value2")
        sm.clear()
        assert sm.has("key1") is False
        assert sm.has("key2") is False

    def test_get_all(self):
        """测试获取所有状态"""
        from core.state_manager import StateManager
        sm = StateManager()
        sm.set("a", 1)
        sm.set("b", 2)
        all_states = sm.get_all()
        assert all_states["a"] == 1
        assert all_states["b"] == 2


class TestLifecycle:
    """生命周期测试"""

    def test_import(self):
        """测试生命周期可导入"""
        from core.lifecycle import LifecycleManager
        assert LifecycleManager is not None


class TestPluginBase:
    """插件基类测试"""

    def test_import(self):
        """测试插件基类可导入"""
        from core.plugin_base import PluginBase
        assert PluginBase is not None