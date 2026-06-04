# -*- coding: utf-8 -*-
"""utils.config 模块单元测试"""
import os
import sys
import pytest

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.config import Config, config


class TestConfig:
    """配置加载测试"""

    def test_singleton(self):
        """验证Config为单例模式"""
        c1 = Config()
        c2 = Config()
        assert c1 is c2

    def test_default_values(self):
        """验证默认值正确加载"""
        # 使用独立实例避免缓存影响
        # 由于是单例，验证已有config实例的默认值
        assert config.MAX_BATCH_SIZE == 100
        assert config.MAX_RETRY_COUNT == 3
        assert config.RETRY_INTERVAL == 5
        assert config.TASK_STATUS_FILE == "status/task_runtime_status.json"

    def test_llm_defaults(self):
        """验证LLM配置默认值"""
        assert config.DEFAULT_LLM_PROVIDER == "qwen"
        assert "dashscope" in config.DASHSCOPE_API_BASE

    def test_mysql_defaults(self):
        """验证MySQL配置默认值"""
        assert config.MYSQL_HOST == "localhost"
        assert config.MYSQL_PORT == 3306
        assert config.MYSQL_DATABASE == "ai_docagent"

    def test_mongo_defaults(self):
        """验证MongoDB配置默认值"""
        assert config.MONGO_HOST == "localhost"
        assert config.MONGO_PORT == 27017
        assert config.MONGO_COLLECTION == "raw_documents"

    def test_redis_defaults(self):
        """验证Redis配置默认值"""
        assert config.REDIS_HOST == "localhost"
        assert config.REDIS_PORT == 6379
        assert config.REDIS_DB == 0

    def test_log_defaults(self):
        """验证日志配置默认值"""
        assert config.LOG_LEVEL == "INFO"
        assert config.LOG_DIR == "logs/"

    def test_env_override(self, monkeypatch):
        """验证环境变量可以覆盖默认配置"""
        monkeypatch.setenv("MAX_BATCH_SIZE", "50")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "zhipu")
        monkeypatch.setenv("MYSQL_HOST", "192.168.1.1")

        c = Config()
        c.reload()

        assert c.MAX_BATCH_SIZE == 50
        assert c.DEFAULT_LLM_PROVIDER == "zhipu"
        assert c.MYSQL_HOST == "192.168.1.1"

        # 恢复
        monkeypatch.delenv("MAX_BATCH_SIZE")
        monkeypatch.delenv("DEFAULT_LLM_PROVIDER")
        monkeypatch.delenv("MYSQL_HOST")
        c.reload()

    def test_reload(self, monkeypatch):
        """验证reload方法可以重新加载配置"""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        config.reload()
        assert config.LOG_LEVEL == "DEBUG"
        # 恢复
        monkeypatch.delenv("LOG_LEVEL")
        config.reload()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
