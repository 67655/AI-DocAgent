# -*- coding: utf-8 -*-
"""validator 模块单元测试"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validator.rule_validator import RuleValidator, ValidationResult, ValidationLevel
from validator.dedup_validator import DedupValidator
from validator.validator import QualityValidator, quality_validator


# ============================
# ValidationResult 测试
# ============================
class TestValidationResult:
    def test_pass(self):
        r = ValidationResult(level=ValidationLevel.INFO, message="OK")
        assert r.is_valid() is True

    def test_fail(self):
        r = ValidationResult(level=ValidationLevel.ERROR, message="失败")
        assert r.is_valid() is False

    def test_warning_is_valid(self):
        r = ValidationResult(level=ValidationLevel.WARNING, message="警告")
        assert r.is_valid() is True  # WARNING不算失败

    def test_to_dict(self):
        r = ValidationResult(field="title", level=ValidationLevel.ERROR,
                             message="不能为空", rule_name="required")
        d = r.to_dict()
        assert d["field"] == "title"
        assert d["pass"] is False


# ============================
# RuleValidator 测试
# ============================
class TestRuleValidator:
    def setup_method(self):
        self.v = RuleValidator()

    def test_required_pass(self):
        self.v.add_required_rule("name")
        results = self.v.validate_one({"name": "张三"})
        assert self.v.is_all_valid(results)

    def test_required_fail(self):
        self.v.add_required_rule("name")
        results = self.v.validate_one({"name": ""})
        assert not self.v.is_all_valid(results)

    def test_type_check(self):
        self.v.add_type_rule("count", int)
        assert self.v.is_all_valid(self.v.validate_one({"count": 42}))
        assert not self.v.is_all_valid(self.v.validate_one({"count": "not_int"}))

    def test_regex_rule(self):
        self.v.add_regex_rule("email", r'^[\w.]+@\w+\.\w+$')
        assert self.v.is_all_valid(self.v.validate_one({"email": "test@example.com"}))
        assert not self.v.is_all_valid(self.v.validate_one({"email": "invalid"}))

    def test_length_rule(self):
        self.v.add_length_rule("code", min_len=3, max_len=6)
        assert self.v.is_all_valid(self.v.validate_one({"code": "ABC123"}))
        assert not self.v.is_all_valid(self.v.validate_one({"code": "AB"}))

    def test_range_rule(self):
        self.v.add_range_rule("score", min_val=0, max_val=100)
        assert self.v.is_all_valid(self.v.validate_one({"score": 85}))
        assert not self.v.is_all_valid(self.v.validate_one({"score": 150}))

    def test_custom_rule(self):
        self.v.add_custom_rule("code", "alphanumeric",
                               lambda v: str(v).isalnum() if v else True)
        assert self.v.is_all_valid(self.v.validate_one({"code": "ABC123"}))
        assert not self.v.is_all_valid(self.v.validate_one({"code": "ABC-123"}))

    def test_validate_batch(self):
        self.v.add_required_rule("x")
        data_list = [{"x": "ok"}, {"x": ""}, {"x": "ok2"}]
        results = self.v.validate_batch(data_list)
        assert len(results) == 3
        assert self.v.is_all_valid(results[0])
        assert not self.v.is_all_valid(results[1])

    def test_filter_valid(self):
        self.v.add_required_rule("field")
        data = [{"field": "v1"}, {"field": ""}, {"field": "v2"}]
        valid, invalid = self.v.filter_valid(data)
        assert len(valid) == 2
        assert len(invalid) == 1

    def test_multi_rule_on_one_field(self):
        self.v.add_required_rule("email")
        self.v.add_regex_rule("email", r'^\S+@\S+\.\S+$')
        # 空值 + 格式错误
        results = self.v.validate_one({"email": ""})
        errors = [r for r in results if not r.is_valid()]
        assert len(errors) >= 1  # 至少required失败

    def test_get_rules_summary(self):
        self.v.add_required_rule("a")
        self.v.add_regex_rule("b", r'\d+')
        summary = self.v.get_rules_summary()
        assert "a" in summary
        assert "b" in summary


# ============================
# DedupValidator 测试
# ============================
class TestDedupValidator:
    def setup_method(self):
        from utils.md5_utils import MD5Deduplicator
        self.dedup = DedupValidator(deduplicator=MD5Deduplicator())

    def test_first_content_not_duplicate(self):
        result = self.dedup.check_content_duplicate("新内容A", doc_id="001")
        assert result["is_duplicate"] is False

    def test_duplicate_content_detected(self):
        self.dedup.check_content_duplicate("重复内容", doc_id="001")
        result = self.dedup.check_content_duplicate("重复内容", doc_id="002")
        assert result["is_duplicate"] is True
        assert result["existing_doc_id"] == "001"

    def test_field_duplicate(self):
        self.dedup.check_field_duplicate({"title": "唯一标题"}, "title", doc_id="1")
        result = self.dedup.check_field_duplicate({"title": "唯一标题"}, "title", doc_id="2")
        assert result["is_duplicate"] is True

    def test_dedup_batch(self):
        data = [
            {"id": 1, "text": "content_A"},
            {"id": 2, "text": "content_B"},
            {"id": 3, "text": "content_A"},  # 重复
            {"id": 4, "text": "content_C"},
        ]
        unique, dups = self.dedup.dedup_batch(data, dedup_field="text")
        assert len(unique) == 3
        assert len(dups) == 1
        assert dups[0]["data"]["id"] == 3

    def test_get_fingerprint(self):
        fp1 = self.dedup.get_fingerprint("hello")
        fp2 = self.dedup.get_fingerprint("hello")
        assert fp1 == fp2
        assert len(fp1) == 32


# ============================
# QualityValidator 测试
# ============================
class TestQualityValidator:
    def setup_method(self):
        from utils.md5_utils import MD5Deduplicator
        self.qv = QualityValidator(
            rule_validator=RuleValidator(),
            dedup_validator=DedupValidator(deduplicator=MD5Deduplicator()),
            recheck_threshold=0.7,
        )
        self.qv.rule_validator.add_required_rule("title")
        self.qv.rule_validator.add_type_rule("score", int)

    def test_validate_pass(self):
        report = self.qv.validate({"title": "测试", "score": 95}, doc_id="d1")
        assert report["pass"] is True
        assert report["needs_recheck"] is False

    def test_validate_rule_fail(self):
        report = self.qv.validate({"title": "", "score": "bad"}, doc_id="d2")
        assert report["pass"] is False

    def test_validate_dedup(self):
        self.qv.validate({"title": "唯一文档", "score": 80}, doc_id="d1")
        report = self.qv.validate({"title": "唯一文档", "score": 80}, doc_id="d2")
        assert report["pass"] is False

    def test_low_confidence_needs_recheck(self):
        report = self.qv.validate(
            {"title": "低置信度", "score": 50, "confidence": 0.3}, doc_id="d3"
        )
        assert report["needs_recheck"] is True

    def test_high_confidence_no_recheck(self):
        report = self.qv.validate(
            {"title": "高置信度", "score": 90, "confidence": 0.9}, doc_id="d4"
        )
        assert report["needs_recheck"] is False

    def test_error_archive(self):
        self.qv.clear()
        self.qv.validate({"title": "", "score": 0}, doc_id="bad")
        archive = self.qv.get_error_archive()
        assert len(archive) >= 1

    def test_recheck_queue(self):
        self.qv.clear()
        self.qv.validate({"title": "低分", "score": 10, "confidence": 0.3}, doc_id="low")
        queue = self.qv.get_recheck_queue()
        assert len(queue) >= 1
        assert queue[0]["confidence"] == 0.3

    def test_validate_batch(self):
        self.qv.clear()
        data = [
            {"title": "A", "score": 100},
            {"title": "", "score": 0},       # 规则失败
            {"title": "A", "score": 100},    # 重复
        ]
        summary = self.qv.validate_batch(data)
        assert summary["total"] == 3
        assert summary["passed"] <= 2  # 最多2条通过

    def test_export_error_archive(self):
        self.qv.clear()
        self.qv.validate({"title": "", "score": -1}, doc_id="err")
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "errors.json")
            self.qv.export_error_archive(path)
            assert os.path.exists(path)
            import json
            with open(path) as f:
                exported = json.load(f)
            assert exported["count"] >= 1
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_global_validator(self):
        assert isinstance(quality_validator, QualityValidator)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
