"""工具模块单元测试"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestLogger:
    """日志工具测试"""

    def test_import(self):
        """测试日志模块可导入"""
        from utils.logger import get_logger, setup_logger
        assert get_logger is not None
        assert setup_logger is not None

    def test_get_logger(self):
        """测试获取日志器"""
        from utils.logger import get_logger
        logger = get_logger("test")
        assert logger is not None
        assert logger.name == "test"


class TestExceptions:
    """异常定义测试"""

    def test_import(self):
        """测试异常模块可导入"""
        from utils.exceptions import AgentError, ConfigError, ToolError, SkillError
        assert AgentError is not None
        assert issubclass(ConfigError, AgentError)
        assert issubclass(ToolError, AgentError)
        assert issubclass(SkillError, AgentError)

    def test_config_error(self):
        """测试配置异常"""
        from utils.exceptions import ConfigError
        err = ConfigError("配置错误")
        assert str(err) == "配置错误"

    def test_tool_error(self):
        """测试工具异常"""
        from utils.exceptions import ToolError
        err = ToolError("工具执行失败")
        assert str(err) == "工具执行失败"


class TestSingleton:
    """单例装饰器测试"""

    def test_import(self):
        """测试单例装饰器可导入"""
        from utils.singleton import singleton
        assert singleton is not None

    def test_singleton_decorator(self):
        """测试单例装饰器"""
        from utils.singleton import singleton

        @singleton
        class TestClass:
            pass

        obj1 = TestClass()
        obj2 = TestClass()
        assert obj1 is obj2


class TestStringUtils:
    """字符串工具测试"""

    def test_import(self):
        """测试字符串工具可导入"""
        from utils.string_utils import truncate, slugify
        assert truncate is not None
        assert slugify is not None

    def test_truncate(self):
        """测试截断字符串"""
        from utils.string_utils import truncate
        assert truncate("hello world", 5) == "hello..."
        assert truncate("short", 10) == "short"

    def test_slugify(self):
        """测试生成 slug"""
        from utils.string_utils import slugify
        assert slugify("Hello World") == "hello-world"
        assert slugify("Test 123") == "test-123"


class TestFileUtils:
    """文件工具测试"""

    def test_import(self):
        """测试文件工具可导入"""
        from utils.file_utils import ensure_dir, safe_read
        assert ensure_dir is not None
        assert safe_read is not None


class TestValidator:
    """验证器测试"""

    def test_import(self):
        """测试验证器可导入"""
        from utils.validator import is_valid_url, is_valid_email
        assert is_valid_url is not None
        assert is_valid_email is not None