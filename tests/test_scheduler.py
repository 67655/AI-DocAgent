# -*- coding: utf-8 -*-
"""scheduler 模块单元测试"""
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scheduler.task_status import (
    TaskRuntimeStatus,
    TaskStatus,
    ShardStatus,
)
from scheduler.batch_manager import BatchManager
from scheduler.scheduler import TaskScheduler, scheduler


# ============================
# TaskRuntimeStatus 测试
# ============================
class TestTaskRuntimeStatus:
    """task_runtime_status.json 状态管理测试"""

    def setup_method(self):
        """每个测试前创建临时状态文件"""
        self.tmp_dir = tempfile.mkdtemp()
        self.status_file = os.path.join(self.tmp_dir, "test_status.json")

    def teardown_method(self):
        """清理临时文件"""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_init_empty(self):
        """测试初始化空状态"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        assert status._data["total_count"] == 0
        assert status._data["completed_count"] == 0
        assert status._data["status"] == TaskStatus.PENDING.value

    def test_init_batch(self):
        """测试批次初始化"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_001", "测试批次", total_count=25, shard_size=10)

        data = status.get_full_status()
        assert data["batch_id"] == "batch_001"
        assert data["total_count"] == 25
        assert len(data["shards"]) == 3  # 10+10+5
        assert data["shards"][0]["start_index"] == 0
        assert data["shards"][0]["end_index"] == 9
        assert data["shards"][2]["end_index"] == 24

    def test_get_pending_shards(self):
        """测试获取待处理分片"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_001", "测试", total_count=20, shard_size=5)

        pending = status.get_pending_shards()
        assert len(pending) == 4  # 20/5=4个分片全部待处理

    def test_shard_lifecycle(self):
        """测试分片完整生命周期"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_002", "生命周期测试", total_count=10, shard_size=5)

        # 开始分片
        status.start_shard("shard_0000")
        data = status.get_full_status()
        assert data["shards"][0]["status"] == ShardStatus.RUNNING.value

        # 完成分片
        status.complete_shard("shard_0000", processed_count=5, last_index=4)
        data = status.get_full_status()
        assert data["shards"][0]["status"] == ShardStatus.COMPLETED.value
        assert data["completed_count"] == 5

    def test_fail_shard(self):
        """测试分片失败标记"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_003", "失败测试", total_count=10, shard_size=5)

        status.fail_shard("shard_0000", error="模拟处理异常")
        data = status.get_full_status()
        assert data["shards"][0]["status"] == ShardStatus.FAILED.value
        assert "模拟处理异常" in data["shards"][0]["error"]

    def test_record_failed_item(self):
        """测试记录失败任务"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_004", "失败记录测试", total_count=5, shard_size=5)

        status.record_failed_item(item_index=2, error="API超时", retry_count=1)
        failed = status.get_failed_items_for_retry(max_retry=3)
        assert len(failed) == 1
        assert failed[0]["index"] == 2
        assert failed[0]["retry_count"] == 1

    def test_get_failed_items_max_retry_filter(self):
        """测试重试次数过滤"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_005", "过滤测试", total_count=10, shard_size=5)

        status.record_failed_item(item_index=1, error="错误1", retry_count=1)
        status.record_failed_item(item_index=2, error="错误2", retry_count=3)

        retryable = status.get_failed_items_for_retry(max_retry=3)
        assert len(retryable) == 1
        assert retryable[0]["index"] == 1  # 只有retry_count=1的可以重试

    def test_get_progress(self):
        """测试进度查询"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_006", "进度测试", total_count=100, shard_size=10)

        progress = status.get_progress()
        assert progress["total"] == 100
        assert progress["completed"] == 0
        assert progress["progress_pct"] == 0.0
        assert progress["shard_count"] == 10

    def test_complete_batch(self):
        """测试批次完成判断"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_007", "完成测试", total_count=5, shard_size=5)

        status.complete_shard("shard_0000", processed_count=5, last_index=4)
        data = status.get_full_status()
        assert data["status"] == TaskStatus.COMPLETED.value

    # ========== 断点续传核心测试 ==========

    def test_is_resume_true(self):
        """测试断点续传检测 - 有已完成进度"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_008", "续传测试", total_count=20, shard_size=5)
        status.complete_shard("shard_0000", processed_count=5, last_index=4)

        # 重新加载状态文件
        status2 = TaskRuntimeStatus(status_file=self.status_file)
        assert status2.is_resume() is True

    def test_is_resume_false_new_batch(self):
        """测试断点续传检测 - 全新批次"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_009", "新批次", total_count=10, shard_size=5)
        assert status.is_resume() is False

    def test_resume_skips_completed_shards(self):
        """核心测试：断点续传自动跳过已完成分片"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_010", "续传跳过测试", total_count=20, shard_size=5)
        # 标记前2个分片为已完成
        status.complete_shard("shard_0000", processed_count=5, last_index=4)
        status.complete_shard("shard_0001", processed_count=5, last_index=9)

        # 重新加载（模拟重启）
        status2 = TaskRuntimeStatus(status_file=self.status_file)
        pending = status2.get_pending_shards()
        assert len(pending) == 2  # 只有shard_0002和shard_0003
        assert pending[0]["shard_id"] == "shard_0002"
        assert pending[0]["start_index"] == 10

    def test_interrupted_running_shard_retried(self):
        """测试中断的RUNNING分片被重新调度"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_011", "中断测试", total_count=10, shard_size=5)
        status.start_shard("shard_0000")

        # 模拟程序崩溃后重新加载
        status2 = TaskRuntimeStatus(status_file=self.status_file)
        pending = status2.get_pending_shards()
        # shard_0000 应从 RUNNING 重置为 PENDING 并加入待处理
        assert any(s["shard_id"] == "shard_0000" for s in pending)

    def test_export_summary(self):
        """测试导出摘要"""
        status = TaskRuntimeStatus(status_file=self.status_file)
        status.init_batch("batch_012", "摘要测试", total_count=10, shard_size=5)
        status.complete_shard("shard_0000", processed_count=5, last_index=4)

        summary = status.export_summary()
        data = json.loads(summary)
        assert data["batch_id"] == "batch_012"
        assert data["completed_count"] == 5
        assert data["total_count"] == 10


# ============================
# BatchManager 测试
# ============================
class TestBatchManager:
    """批次管理器测试"""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.status_file = os.path.join(self.tmp_dir, "batch_status.json")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_batch(self):
        """测试创建批次"""
        manager = BatchManager(status_file=self.status_file, default_shard_size=5)
        items = list(range(15))
        batch_id = manager.create_batch(items, batch_name="单元测试批次")

        assert batch_id.startswith("batch_")
        progress = manager.get_progress()
        assert progress["total"] == 15
        assert progress["shard_count"] == 3

    def test_run_batch_all_success(self):
        """测试批量执行 - 全部成功"""
        manager = BatchManager(status_file=self.status_file, default_shard_size=5)
        items = list(range(10))

        def process(item):
            return {"index": item, "result": item * 2}

        result = manager.run_batch(
            items=items,
            process_func=process,
            batch_name="全部成功测试",
        )

        assert result["completed"] == 10
        assert result["failed"] == 0
        assert result["progress_pct"] == 100.0

    def test_run_batch_with_failures(self):
        """测试批量执行 - 部分失败"""
        manager = BatchManager(status_file=self.status_file, default_shard_size=5)
        items = list(range(10))

        def process(item):
            if item == 3 or item == 7:
                raise ValueError(f"模拟失败: {item}")
            return {"index": item}

        result = manager.run_batch(
            items=items,
            process_func=process,
            batch_name="部分失败测试",
        )

        assert result["completed"] == 8
        assert result["failed"] > 0

    def test_resume_from_interruption(self):
        """测试从中断恢复（断点续传端到端）"""
        items = list(range(20))
        processed_items = []

        def process(item):
            if item == 12:
                raise RuntimeError("模拟在索引12处崩溃")
            processed_items.append(item)
            return {"index": item}

        # 第一次执行：在索引12处失败
        manager1 = BatchManager(status_file=self.status_file, default_shard_size=5)
        manager1.run_batch(items=items, process_func=process, batch_name="中断恢复测试")

        # 验证前12个之前的数据已处理
        assert len(processed_items) >= 10

        # 第二次执行：从状态文件恢复
        processed_after_resume = []

        def process_resume(item):
            processed_after_resume.append(item)
            return {"index": item}

        manager2 = BatchManager(status_file=self.status_file, default_shard_size=5)
        manager2.run_batch(
            items=items,
            process_func=process_resume,
            batch_name="中断恢复测试",
        )

        # 恢复后处理了剩余数据
        total_processed = len(processed_items) + len(processed_after_resume)
        # 至少应该有19个（除了索引12可能失败）
        assert total_processed >= 18


# ============================
# TaskScheduler 测试
# ============================
class TestTaskScheduler:
    """全局调度器测试"""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.status_file = os.path.join(self.tmp_dir, "scheduler_status.json")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_and_run(self):
        """测试创建并运行批次"""
        items = ["a", "b", "c", "d", "e"]

        def process(item):
            return {"item": item, "upper": item.upper()}

        result = scheduler.create_and_run(
            items=items,
            process_func=process,
            batch_name="调度器测试",
            shard_size=3,
            status_file=self.status_file,
        )

        assert result["total"] == 5
        assert result["completed"] == 5
        assert result["progress_pct"] == 100.0

    def test_resume(self):
        """测试显式断点续传"""
        # 先执行部分
        items = list(range(10))
        processed = []

        def process(item):
            if item == 7:
                raise RuntimeError("模拟崩溃")
            processed.append(item)
            return {"index": item}

        scheduler.create_and_run(
            items=items,
            process_func=process,
            shard_size=3,
            status_file=self.status_file,
        )

        completed_before = len(processed)

        # 恢复执行
        def process_resume(item):
            return {"index": item}

        result = scheduler.resume(
            items=items,
            process_func=process_resume,
            status_file=self.status_file,
        )

        assert result["completed"] >= completed_before

    def test_load_status(self):
        """测试加载历史状态"""
        # 先创建一个批次并执行
        items = list(range(5))
        scheduler.create_and_run(
            items=items,
            process_func=lambda x: {"i": x},
            status_file=self.status_file,
        )

        # 加载状态文件
        status = scheduler.load_status(self.status_file)
        assert status.get_full_status()["total_count"] == 5
        assert status.get_full_status()["status"] == TaskStatus.COMPLETED.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
