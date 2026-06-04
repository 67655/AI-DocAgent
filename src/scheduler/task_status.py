# -*- coding: utf-8 -*-
"""
任务状态管理模块
基于 task_runtime_status.json 实现断点续传状态记录
"""
import json
import os
import threading
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    """任务执行状态枚举"""
    PENDING = "pending"         # 等待执行
    RUNNING = "running"         # 执行中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    PAUSED = "paused"           # 已暂停
    CANCELLED = "cancelled"     # 已取消


class ShardStatus(str, Enum):
    """分片执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskRuntimeStatus:
    """
    任务运行时状态管理器
    核心数据结构：task_runtime_status.json
    支持断点续传：任务重启动后自动跳过已完成分片
    """

    def __init__(self, status_file: Optional[str] = None):
        """
        Args:
            status_file: 状态文件路径（默认使用配置值）
        """
        self._status_file = status_file or config.TASK_STATUS_FILE
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = self._init_empty_status()
        self._dirty = False  # 标记是否有未持久化的变更

        # 尝试加载已有状态文件（断点续传关键）
        if os.path.exists(self._status_file):
            self._load()
            logger.info(f"加载已有任务状态文件: {self._status_file}")
        else:
            logger.info(f"创建新的任务状态文件: {self._status_file}")

    def _init_empty_status(self) -> dict:
        """初始化空的状态数据结构"""
        return {
            "batch_id": "",
            "batch_name": "",
            "total_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "status": TaskStatus.PENDING.value,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "shards": [],
            "failed_items": [],
        }

    def _load(self):
        """从磁盘加载状态文件"""
        try:
            with open(self._status_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # 合并默认值，防止旧格式字段缺失
                default = self._init_empty_status()
                default.update(loaded)
                self._data = default
            logger.debug(f"状态文件加载成功，已完成: {self._data['completed_count']}/{self._data['total_count']}")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"状态文件加载失败，使用空状态: {e}")
            self._data = self._init_empty_status()

    def _save(self):
        """持久化状态到磁盘"""
        self._data["updated_at"] = datetime.now().isoformat()
        # 确保目录存在
        os.makedirs(os.path.dirname(self._status_file), exist_ok=True)
        with open(self._status_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        self._dirty = False

    def save(self):
        """公开的保存方法（自动加锁）"""
        with self._lock:
            self._save()

    def init_batch(self, batch_id: str, batch_name: str, total_count: int, shard_size: int = 10):
        """
        初始化新批次任务

        Args:
            batch_id: 批次唯一标识
            batch_name: 批次名称
            total_count: 总任务数量
            shard_size: 每分片包含的任务数
        """
        with self._lock:
            self._data = self._init_empty_status()
            self._data["batch_id"] = batch_id
            self._data["batch_name"] = batch_name
            self._data["total_count"] = total_count
            self._data["status"] = TaskStatus.PENDING.value

            # 按分片大小切分任务
            shards = []
            for i in range(0, total_count, shard_size):
                end = min(i + shard_size, total_count)
                shards.append({
                    "shard_id": f"shard_{len(shards):04d}",
                    "start_index": i,
                    "end_index": end - 1,
                    "status": ShardStatus.PENDING.value,
                    "processed_count": 0,
                    "failed_count": 0,
                    "last_processed_index": None,
                })
            self._data["shards"] = shards
            self._save()
            logger.info(f"批次初始化完成: {batch_id}, 共{total_count}个任务, {len(shards)}个分片")

    def get_pending_shards(self) -> List[Dict]:
        """
        获取所有待处理的分片（断点续传核心方法）
        返回 PENDING 和 FAILED 状态的分片，
        RUNNING 状态的分片视为中断需要重新处理
        """
        with self._lock:
            pending = []
            for shard in self._data["shards"]:
                if shard["status"] in (ShardStatus.PENDING.value, ShardStatus.FAILED.value):
                    pending.append(shard)
                elif shard["status"] == ShardStatus.RUNNING.value:
                    # 上次执行中断，重置为待处理
                    logger.warning(
                        f"检测到中断分片 {shard['shard_id']}（上次处理到索引"
                        f" {shard.get('last_processed_index', '未知')}），重新调度"
                    )
                    shard["status"] = ShardStatus.PENDING.value
                    shard["last_processed_index"] = None
                    pending.append(shard)
            self._save()
            return pending

    def get_skipped_count(self) -> int:
        """获取已完成的分片/任务数量（用于断点续传统计）"""
        with self._lock:
            completed = sum(
                1 for s in self._data["shards"]
                if s["status"] == ShardStatus.COMPLETED.value
            )
            return completed

    def start_shard(self, shard_id: str):
        """标记分片开始执行"""
        with self._lock:
            shard = self._find_shard(shard_id)
            if shard:
                shard["status"] = ShardStatus.RUNNING.value
                shard["last_processed_index"] = shard.get("last_processed_index") or shard["start_index"]
                self._data["status"] = TaskStatus.RUNNING.value
                self._save()

    def complete_shard(self, shard_id: str, processed_count: int, last_index: int):
        """标记分片执行完成"""
        with self._lock:
            shard = self._find_shard(shard_id)
            if shard:
                shard["status"] = ShardStatus.COMPLETED.value
                shard["processed_count"] = processed_count
                shard["last_processed_index"] = last_index
                self._data["completed_count"] = sum(
                    s.get("processed_count", 0) for s in self._data["shards"]
                    if s["status"] == ShardStatus.COMPLETED.value
                )
                self._data["skipped_count"] = self._data["total_count"] - self._data["completed_count"] - self._data["failed_count"]
                self._check_batch_complete()
                self._save()
                logger.info(
                    f"分片完成: {shard_id}, "
                    f"进度: {self._data['completed_count']}/{self._data['total_count']}"
                )

    def fail_shard(self, shard_id: str, error: str, failed_items: Optional[List[Dict]] = None):
        """标记分片执行失败"""
        with self._lock:
            shard = self._find_shard(shard_id)
            if shard:
                shard["status"] = ShardStatus.FAILED.value
                shard["error"] = error
                self._data["failed_count"] += shard.get("failed_count", 0)
                if failed_items:
                    self._data["failed_items"].extend(failed_items)
                self._save()
                logger.error(f"分片失败: {shard_id}, 错误: {error}")

    def record_failed_item(self, item_index: int, error: str, retry_count: int = 0):
        """记录单个失败任务"""
        with self._lock:
            # 检查是否已存在，更新重试次数
            for item in self._data["failed_items"]:
                if item["index"] == item_index:
                    item["retry_count"] = retry_count
                    item["last_error"] = error
                    item["last_attempt_at"] = datetime.now().isoformat()
                    self._save()
                    return
            # 新增失败记录
            self._data["failed_items"].append({
                "index": item_index,
                "error": error,
                "retry_count": retry_count,
                "first_failed_at": datetime.now().isoformat(),
                "last_error": error,
                "last_attempt_at": datetime.now().isoformat(),
            })
            self._save()

    def get_failed_items_for_retry(self, max_retry: int = 3) -> List[Dict]:
        """
        获取可重试的失败任务
        只返回重试次数未超过阈值的失败项

        Args:
            max_retry: 最大重试次数阈值

        Returns:
            可重试的失败项列表
        """
        with self._lock:
            return [
                item for item in self._data["failed_items"]
                if item["retry_count"] < max_retry
            ]

    def set_batch_status(self, status: TaskStatus):
        """设置批次整体状态"""
        with self._lock:
            self._data["status"] = status.value
            self._save()

    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度摘要"""
        with self._lock:
            total = self._data["total_count"]
            completed = self._data["completed_count"]
            failed = self._data["failed_count"]
            return {
                "batch_id": self._data["batch_id"],
                "batch_name": self._data["batch_name"],
                "status": self._data["status"],
                "total": total,
                "completed": completed,
                "failed": failed,
                "pending": total - completed - failed,
                "progress_pct": round(completed / total * 100, 2) if total > 0 else 0,
                "shard_count": len(self._data["shards"]),
                "completed_shards": sum(
                    1 for s in self._data["shards"]
                    if s["status"] == ShardStatus.COMPLETED.value
                ),
            }

    def get_full_status(self) -> Dict[str, Any]:
        """获取完整状态数据（只读副本）"""
        with self._lock:
            import copy
            return copy.deepcopy(self._data)

    def is_resume(self) -> bool:
        """
        判断当前是否为断点续传场景
        条件：状态文件存在，且已有部分任务完成
        """
        with self._lock:
            return (
                self._data["completed_count"] > 0
                and self._data["status"] != TaskStatus.COMPLETED.value
            )

    def _find_shard(self, shard_id: str) -> Optional[Dict]:
        """根据shard_id查找分片"""
        for shard in self._data["shards"]:
            if shard["shard_id"] == shard_id:
                return shard
        return None

    def _check_batch_complete(self):
        """检查批次是否全部完成"""
        all_done = all(
            s["status"] in (ShardStatus.COMPLETED.value, ShardStatus.FAILED.value)
            for s in self._data["shards"]
        )
        if all_done:
            if self._data["failed_count"] == 0:
                self._data["status"] = TaskStatus.COMPLETED.value
                logger.info(f"✅ 批次 {self._data['batch_id']} 全部完成！")
            else:
                self._data["status"] = TaskStatus.COMPLETED.value
                logger.warning(
                    f"⚠️ 批次 {self._data['batch_id']} 完成（含"
                    f" {self._data['failed_count']} 个失败项）"
                )

    def export_summary(self) -> str:
        """导出批次完成摘要JSON字符串"""
        summary = {
            "batch_id": self._data["batch_id"],
            "batch_name": self._data["batch_name"],
            "total_count": self._data["total_count"],
            "completed_count": self._data["completed_count"],
            "failed_count": self._data["failed_count"],
            "status": self._data["status"],
            "duration": None,
        }
        if self._data.get("created_at") and self._data.get("updated_at"):
            try:
                start = datetime.fromisoformat(self._data["created_at"])
                end = datetime.fromisoformat(self._data["updated_at"])
                summary["duration_seconds"] = (end - start).total_seconds()
            except (ValueError, TypeError):
                pass
        return json.dumps(summary, ensure_ascii=False, indent=2)
