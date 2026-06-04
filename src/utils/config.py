# -*- coding: utf-8 -*-
"""
配置加载工具
从环境变量加载项目全局配置，所有敏感信息通过 .env 文件注入
"""
import os
from typing import Optional


class Config:
    """全局配置管理类（单例模式）"""

    _instance: Optional["Config"] = None

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_config()

    def _load_config(self):
        """从环境变量加载所有配置项"""
        # LLM API 配置
        self.DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
        self.DASHSCOPE_API_BASE = os.getenv("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/api/v1")
        self.ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
        self.ZHIPU_API_BASE = os.getenv("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "qwen")

        # MySQL 配置
        self.MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
        self.MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
        self.MYSQL_USER = os.getenv("MYSQL_USER", "root")
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
        self.MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ai_docagent")

        # MongoDB 配置
        self.MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
        self.MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
        self.MONGO_USER = os.getenv("MONGO_USER", "admin")
        self.MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")
        self.MONGO_DATABASE = os.getenv("MONGO_DATABASE", "ai_docagent")
        self.MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "raw_documents")

        # Redis 配置
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
        self.REDIS_DB = int(os.getenv("REDIS_DB", "0"))

        # 任务调度配置
        self.MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "100"))
        self.MAX_RETRY_COUNT = int(os.getenv("MAX_RETRY_COUNT", "3"))
        self.RETRY_INTERVAL = int(os.getenv("RETRY_INTERVAL", "5"))
        self.TASK_STATUS_FILE = os.getenv("TASK_STATUS_FILE", "status/task_runtime_status.json")

        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_DIR = os.getenv("LOG_DIR", "logs/")

    def reload(self):
        """重新加载配置（用于配置变更后热更新）"""
        self._load_config()


# 全局配置实例
config = Config()
