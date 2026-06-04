# -*- coding: utf-8 -*-
"""utils.logger 模块单元测试"""
import os
import sys
import logging
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestLoggerManager:
    """日志管理器测试"""

    def test_get_logger(self):
        """测试获取logger"""
        from utils.logger import LoggerManager

        manager = LoggerManager()
        logger = manager.get_logger("test_unit")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_unit"

    def test_singleton(self):
        """验证LoggerManager单例"""
        from utils.logger import LoggerManager

        m1 = LoggerManager()
        m2 = LoggerManager()
        assert m1 is m2

    def test_logger_reuse(self):
        """验证同名logger复用"""
        from utils.logger import LoggerManager

        manager = LoggerManager()
        logger1 = manager.get_logger("reuse_test")
        logger2 = manager.get_logger("reuse_test")
        assert logger1 is logger2

    def test_different_logger_names(self):
        """验证不同名logger不一样"""
        from utils.logger import LoggerManager

        manager = LoggerManager()
        logger_a = manager.get_logger("logger_a")
        logger_b = manager.get_logger("logger_b")
        assert logger_a is not logger_b

    def test_logger_has_handlers(self):
        """验证logger至少有一个handler"""
        from utils.logger import LoggerManager

        manager = LoggerManager()
        logger = manager.get_logger("handler_test")
        assert len(logger.handlers) >= 1  # 至少控制台handler

    def test_quick_get_logger(self):
        """测试快捷函数get_logger"""
        from utils.logger import get_logger

        logger = get_logger("quick_test")
        assert isinstance(logger, logging.Logger)

    def test_log_level_from_config(self, monkeypatch):
        """验证日志级别从配置读取"""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        # 重新导入以应用新的环境变量
        from utils.config import Config
        Config().reload()

        from utils.logger import LoggerManager
        manager = LoggerManager()
        logger = manager.get_logger("level_test")
        assert logger.level == logging.DEBUG

        # 恢复
        monkeypatch.delenv("LOG_LEVEL")
        Config().reload()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
