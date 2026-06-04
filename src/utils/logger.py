# -*- coding: utf-8 -*-
"""
日志工具模块
提供统一日志管理：控制台输出 + 文件持久化，支持日志轮转
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
from .config import config


class LoggerManager:
    """日志管理器（单例模式）"""

    _instance: Optional["LoggerManager"] = None
    _loggers: dict = {}

    def __new__(cls) -> "LoggerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """确保日志目录存在"""
        log_dir = config.LOG_DIR
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def get_logger(self, name: str = "docagent", log_file: Optional[str] = None) -> logging.Logger:
        """
        获取指定名称的Logger实例

        Args:
            name: 日志记录器名称
            log_file: 日志文件名（可选，默认使用 name.log）

        Returns:
            logging.Logger 实例
        """
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)

        # 避免重复添加handler
        if logger.handlers:
            self._loggers[name] = logger
            return logger

        # 日志格式
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件输出（带轮转：单文件最大10MB，保留5个备份）
        log_dir = config.LOG_DIR
        if log_dir:
            log_file = log_file or f"{name}.log"
            file_path = os.path.join(log_dir, log_file)
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        self._loggers[name] = logger
        return logger


# 全局日志管理器
log_manager = LoggerManager()


def get_logger(name: str = "docagent") -> logging.Logger:
    """快捷获取日志记录器"""
    return log_manager.get_logger(name)
