# -*- coding: utf-8 -*-
"""
任务调度器
统一入口，协调批次管理和状态追踪
后续可集成Redis缓存、MySQL持久化
"""
from typing import Any, Callable, Dict, List, Optional

from .batch_manager import BatchManager
from .task_status import TaskRuntimeStatus, TaskStatus
from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TaskScheduler:
    """
    全局任务调度器（单例模式）
    提供统一的任务调度接口，后续可扩展：
    - Redis缓存运行中任务状态
    - MySQL持久化历史批次信息
    - 多Worker并行处理
    """

    _instance: Optional["TaskScheduler"] = None

    def __new__(cls) -> "TaskScheduler":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._batch_managers: Dict[str, BatchManager] = {}
        self._current_batch_id: Optional[str] = None

    def create_and_run(
        self,
        items: List[Any],
        process_func: Callable[[Any], Dict[str, Any]],
        batch_name: str = "",
        shard_size: Optional[int] = None,
        status_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建并执行一个批处理任务（最常用入口）
        自动处理断点续传

        Args:
            items: 待处理数据列表
            process_func: 单条处理函数
            batch_name: 批次名称
            shard_size: 分片大小
            status_file: 自定义状态文件路径

        Returns:
            执行结果摘要
        """
        manager = BatchManager(
            status_file=status_file,
            default_shard_size=shard_size or 10,
        )
        result = manager.run_batch(
            items=items,
            process_func=process_func,
            batch_name=batch_name,
            shard_size=shard_size,
        )
        self._current_batch_id = result["batch_id"]
        self._batch_managers[result["batch_id"]] = manager
        return result

    def resume(
        self,
        items: List[Any],
        process_func: Callable[[Any], Dict[str, Any]],
        status_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从已有状态文件恢复执行（显式断点续传）

        Args:
            items: 完整任务列表
            process_func: 处理函数
            status_file: 状态文件路径

        Returns:
            执行结果摘要
        """
        manager = BatchManager(status_file=status_file)
        if not manager.status.is_resume():
            logger.warning("状态文件无已完成进度，将视为新批次执行")
        result = manager.run_batch(items=items, process_func=process_func)
        self._current_batch_id = result["batch_id"]
        self._batch_managers[result["batch_id"]] = manager
        return result

    def get_batch_progress(self, batch_id: Optional[str] = None) -> Optional[Dict]:
        """
        获取批次进度

        Args:
            batch_id: 批次ID（默认使用当前批次）

        Returns:
            进度字典或None
        """
        bid = batch_id or self._current_batch_id
        if bid and bid in self._batch_managers:
            return self._batch_managers[bid].get_progress()
        return None

    def get_batch_summary(self, batch_id: Optional[str] = None) -> Optional[str]:
        """
        获取批次完成摘要JSON

        Args:
            batch_id: 批次ID（默认使用当前批次）

        Returns:
            摘要JSON字符串
        """
        bid = batch_id or self._current_batch_id
        if bid and bid in self._batch_managers:
            return self._batch_managers[bid].export_summary()
        return None

    def load_status(self, status_file: str) -> TaskRuntimeStatus:
        """
        加载指定状态文件（用于只读查看历史批次状态）

        Args:
            status_file: 状态文件路径

        Returns:
            TaskRuntimeStatus实例
        """
        return TaskRuntimeStatus(status_file=status_file)


# 全局调度器实例
scheduler = TaskScheduler()
