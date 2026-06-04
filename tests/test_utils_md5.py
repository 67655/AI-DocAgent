# -*- coding: utf-8 -*-
"""utils.md5_utils 模块单元测试"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.md5_utils import MD5Deduplicator, deduplicator


class TestMD5Computation:
    """MD5计算测试"""

    def test_compute_md5_str(self):
        """测试字符串MD5计算"""
        result = MD5Deduplicator.compute_md5("hello world")
        assert isinstance(result, str)
        assert len(result) == 32
        assert result == "5eb63bbbe01eeed093cb22bb8f5acdc3"  # 已知值

    def test_compute_md5_bytes(self):
        """测试字节MD5计算"""
        result = MD5Deduplicator.compute_md5(b"hello world")
        assert result == "5eb63bbbe01eeed093cb22bb8f5acdc3"

    def test_compute_md5_int(self):
        """测试整型MD5计算（自动转字符串）"""
        result = MD5Deduplicator.compute_md5(12345)
        assert isinstance(result, str)
        assert len(result) == 32

    def test_compute_md5_consistent(self):
        """验证相同内容MD5值一致"""
        r1 = MD5Deduplicator.compute_md5("测试中文内容")
        r2 = MD5Deduplicator.compute_md5("测试中文内容")
        r3 = MD5Deduplicator.compute_md5("不同内容")
        assert r1 == r2
        assert r1 != r3

    def test_compute_md5_file(self):
        """测试文件MD5计算"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("test file content for md5")
            tmp_path = f.name

        try:
            result = MD5Deduplicator.compute_md5_file(tmp_path)
            assert isinstance(result, str)
            assert len(result) == 32
            # 与直接计算内容应一致
            expected = MD5Deduplicator.compute_md5("test file content for md5")
            assert result == expected
        finally:
            os.unlink(tmp_path)

    def test_compute_batch_md5(self):
        """测试批量MD5计算"""
        contents = ["a", "b", "c", "a"]
        results = MD5Deduplicator.compute_batch_md5(contents)
        assert len(results) == 4
        assert results[0] == results[3]  # 相同内容相同指纹
        assert results[0] != results[1]  # 不同内容不同指纹


class TestMD5Deduplicator:
    """MD5去重器测试"""

    def setup_method(self):
        """每个测试前重置去重器"""
        deduplicator.clear()

    def test_is_duplicate_first_time(self):
        """首次插入不应标记为重复"""
        assert deduplicator.is_duplicate("新内容") is False
        assert deduplicator.get_fingerprint_count() == 1

    def test_is_duplicate_second_time(self):
        """重复内容应被检测到"""
        deduplicator.is_duplicate("重复内容")
        assert deduplicator.is_duplicate("重复内容") is True
        assert deduplicator.get_fingerprint_count() == 1  # 指纹数不变

    def test_is_duplicate_with_doc_id(self):
        """带doc_id的去重检查"""
        deduplicator.is_duplicate("文档A内容", doc_id="doc_001")
        fp = MD5Deduplicator.compute_md5("文档A内容")
        assert deduplicator.get_doc_id(fp) == "doc_001"

    def test_register_fingerprint(self):
        """测试手动注册指纹"""
        fp = "abc123def456789012345678901234ab"
        deduplicator.register_fingerprint(fp, doc_id="manual_doc")
        assert deduplicator.get_doc_id(fp) == "manual_doc"
        assert deduplicator.get_fingerprint_count() == 1

    def test_load_fingerprints(self):
        """测试批量加载指纹"""
        fp_list = [
            "fp001",
            ("fp002", "doc_002"),
            "fp003",
            ("fp004", "doc_004"),
        ]
        deduplicator.load_fingerprints(fp_list)
        assert deduplicator.get_fingerprint_count() == 4
        assert deduplicator.get_doc_id("fp002") == "doc_002"
        assert deduplicator.get_doc_id("fp004") == "doc_004"
        assert deduplicator.get_doc_id("fp001") is None

    def test_remove_fingerprint(self):
        """测试移除指纹"""
        deduplicator.register_fingerprint("to_remove", doc_id="tmp")
        assert deduplicator.get_fingerprint_count() == 1
        deduplicator.remove_fingerprint("to_remove")
        assert deduplicator.get_fingerprint_count() == 0
        assert deduplicator.get_doc_id("to_remove") is None

    def test_clear(self):
        """测试清空"""
        deduplicator.is_duplicate("内容1")
        deduplicator.is_duplicate("内容2")
        assert deduplicator.get_fingerprint_count() == 2
        deduplicator.clear()
        assert deduplicator.get_fingerprint_count() == 0

    def test_multiple_unique_contents(self):
        """测试大量唯一内容"""
        for i in range(100):
            assert deduplicator.is_duplicate(f"unique_content_{i}") is False
        assert deduplicator.get_fingerprint_count() == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
