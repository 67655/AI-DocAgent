# -*- coding: utf-8 -*-
"""
批次管理器
负责批次创建、任务分批调度、进度轮询、结果聚合
"""
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .task_status import TaskRuntimeStatus, TaskStatus, ShardStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BatchManager:
    """
    批量任务管理器
    将大批量任务按分片拆解，逐个执行，支持中断恢复
    """

    def __init__(
        self,
        status_file: Optional[str] = None,
        default_shard_size: int = 10,
    ):
        """
        Args:
            status_file: 任务状态文件路径
            default_shard_size: 默认每分片任务数
        """
        self.status = TaskRuntimeStatus(status_file=status_file)
        self.default_shard_size = default_shard_size

    def create_batch(
        self,
        items: List[Any],
        batch_name: str = "",
        shard_size: Optional[int] = None,
    ) -> str:
        """
        创建新批次

        Args:
            items: 待处理的任务数据列表
            batch_name: 批次名称
            shard_size: 每分片任务数（默认使用实例配置）

        Returns:
            batch_id: 批次唯一标识
        """
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        batch_name = batch_name or f"Batch_{datetime.now().strftime('%Y%m%d')}"
        shard_size = shard_size or self.default_shard_size

        self.status.init_batch(
            batch_id=batch_id,
            batch_name=batch_name,
            total_count=len(items),
            shard_size=shard_size,
        )
        return batch_id

    def run_batch(
        self,
        items: List[Any],
        process_func: Callable[[Any], Dict[str, Any]],
        batch_name: str = "",
        shard_size: Optional[int] = None,
        on_shard_complete: Optional[Callable[[Dict], None]] = None,
        on_item_failed: Optional[Callable[[int, Exception], None]] = None,
    ) -> Dict[str, Any]:
        """
        执行批量任务（自动处理断点续传）

        Args:
            items: 待处理的任务数据列表（按索引顺序）
            process_func: 单条任务处理函数，接收item返回结果dict
            batch_name: 批次名称
            shard_size: 每分片大小
            on_shard_complete: 分片完成回调
            on_item_failed: 单条失败回调

        Returns:
            批次执行结果摘要
        """
        # 判断是否为断点续传
        is_resume = self.status.is_resume()

        if is_resume:
            logger.info("🔄 检测到断点续传场景，将跳过已完成分片")
            # 已有batch_id，不再重新创建
        else:
            self.create_batch(items=items, batch_name=batch_name, shard_size=shard_size)

        # 获取待处理分片（自动跳过已完成分片）
        pending_shards = self.status.get_pending_shards()

        if not pending_shards:
            logger.info("所有分片已完成，无需处理")
            return self._build_result()

        completed_count = self.status.get_skipped_count()
        logger.info(
            f"批次 {self.status._data['batch_id']}: "
            f"共{len(self.status._data['shards'])}个分片, "
            f"已完成{completed_count}个, "
            f"待处理{len(pending_shards)}个"
            + (" (断点续传)" if is_resume else "")
        )

        self.status.set_batch_status(TaskStatus.RUNNING)

        for shard in pending_shards:
            shard_id = shard["shard_id"]
            start_idx = shard["start_index"]
            end_idx = shard["end_index"]
            last_processed = shard.get("last_processed_index")

            # 断点续传：从上次中断位置继续
            actual_start = last_processed if last_processed is not None else start_idx
            if actual_start > start_idx:
                logger.info(f"分片 {shard_id} 从索引 {actual_start} 继续（跳过已完成 {actual_start - start_idx} 条）")

            self.status.start_shard(shard_id)
            processed = 0
            failed_in_shard = 0

            for idx in range(actual_start, end_idx + 1):
                item = items[idx]
                try:
                    result = process_func(item)
                    if result:
                        processed += 1
                except Exception as e:
                    failed_in_shard += 1
                    logger.error(f"处理任务索引 {idx} 失败: {e}")
                    self.status.record_failed_item(
                        item_index=idx,
                        error=str(e),
                        retry_count=0,
                    )
                    if on_item_failed:
                        on_item_failed(idx, e)

                # 每处理一条就更新进度（保证断点续传精度）
                if processed % 5 == 0 or idx == end_idx:
                    self.status._data["shards"][
                        int(shard_id.split("_")[1])
                    ]["last_processed_index"] = idx
                    self.status._dirty = True
                    self.status.save()

            if failed_in_shard == 0:
                self.status.complete_shard(shard_id, processed, end_idx)
            else:
                self.status.fail_shard(
                    shard_id,
                    error=f"{failed_in_shard}/{end_idx - actual_start + 1} 条处理失败",
                )

            if on_shard_complete:
                on_shard_complete({
                    "shard_id": shard_id,
                    "processed": processed,
                    "failed": failed_in_shard,
                    "range": f"{actual_start}-{end_idx}",
                })

            progress = self.status.get_progress()
            logger.info(
                f"📊 总体进度: {progress['progress_pct']}% "
                f"({progress['completed']}/{progress['total']})"
            )

        # 检查是否有需要重试的失败项
        retry_items = self.status.get_failed_items_for_retry()
        if retry_items:
            logger.warning(f"存在 {len(retry_items)} 条可重试的失败记录")

        return self._build_result()

    def _build_result(self) -> Dict[str, Any]:
        """构建批次结果摘要"""
        progress = self.status.get_progress()
        return {
            "batch_id": progress["batch_id"],
            "batch_name": progress["batch_name"],
            "status": progress["status"],
            "total": progress["total"],
            "completed": progress["completed"],
            "failed": progress["failed"],
            "pending": progress["pending"],
            "progress_pct": progress["progress_pct"],
        }

    def retry_failed(self, items: List[Any], process_func: Callable, max_retry: int = 3):
        """
        重试失败的任务

        Args:
            items: 原始任务数据列表
            process_func: 处理函数
            max_retry: 最大重试次数
        """
        failed_items = self.status.get_failed_items_for_retry(max_retry)
        if not failed_items:
            logger.info("没有可重试的失败项")
            return

        logger.info(f"重试 {len(failed_items)} 条失败记录...")
        for item_info in failed_items:
            idx = item_info["index"]
            retry_count = item_info["retry_count"]

            try:
                result = process_func(items[idx])
                if result:
                    logger.info(f"重试成功: 索引 {idx} (第{retry_count + 1}次)")
                    # 从失败列表移除
                    self.status._data["failed_items"] = [
                        i for i in self.status._data["failed_items"]
                        if i["index"] != idx
                    ]
            except Exception as e:
                new_retry = retry_count + 1
                if new_retry >= max_retry:
                    logger.error(f"重试耗尽: 索引 {idx}，已达最大重试次数 {max_retry}")
                else:
                    self.status.record_failed_item(idx, str(e), new_retry)

        self.status.save()

    def get_progress(self) -> Dict[str, Any]:
        """获取当前批次进度"""
        return self.status.get_progress()

    def export_summary(self) -> str:
        """导出批次完成摘要"""
        return self.status.export_summary()

    def cancel_batch(self):
        """取消当前批次"""
        self.status.set_batch_status(TaskStatus.CANCELLED)
        logger.warning("批次已取消")
