# -*- coding: utf-8 -*-
"""converter 模块单元测试"""
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from converter.schema import OutputSchema, FieldRule
from converter.field_normalizer import FieldNormalizer
from converter.converter import Converter, converter


# ============================
# FieldNormalizer 测试
# ============================
class TestFieldNormalizer:
    """字段规范化器测试"""

    def setup_method(self):
        self.n = FieldNormalizer()

    # ---- 字符串 ----
    def test_trim(self):
        assert self.n.trim("  hello  ") == "hello"
        assert self.n.trim(None) == ""

    def test_normalize_whitespace(self):
        assert self.n.normalize_whitespace("a   b") == "a b"
        assert self.n.normalize_whitespace("a\n\n\nb") == "a\n\nb"

    def test_remove_html_tags(self):
        assert self.n.remove_html_tags("<p>text</p>") == "text"
        assert self.n.remove_html_tags("<div><span>hello</span></div>") == "hello"

    def test_truncate(self):
        assert self.n.truncate("1234567890", 5) == "12345..."

    def test_to_lower(self):
        assert self.n.to_lower("HELLO") == "hello"

    # ---- 数值 ----
    def test_to_int(self):
        assert self.n.to_int("42") == 42
        assert self.n.to_int("3.7") == 3
        assert self.n.to_int("abc") == 0
        assert self.n.to_int("abc", -1) == -1

    def test_to_float(self):
        assert self.n.to_float("3.14") == 3.14
        assert self.n.to_float("abc") == 0.0

    def test_extract_number(self):
        assert self.n.extract_number("价格是100元") == 100.0
        assert self.n.extract_number("无数字") is None

    # ---- 列表 ----
    def test_to_list_from_str(self):
        assert self.n.to_list("a,b,c") == ["a", "b", "c"]
        assert self.n.to_list("a;b;c") == ["a", "b", "c"]

    def test_to_list_from_list(self):
        assert self.n.to_list([1, 2, 3]) == [1, 2, 3]

    def test_to_list_single(self):
        assert self.n.to_list("hello") == ["hello"]

    def test_deduplicate_list(self):
        assert self.n.deduplicate_list(["a", "b", "a", "c"]) == ["a", "b", "c"]

    # ---- 日期 ----
    def test_to_iso_datetime(self):
        result = self.n.to_iso_datetime("2024-06-04 15:30:00")
        assert "2024-06-04" in result

    # ---- 类型 ----
    def test_normalize_by_type_str(self):
        assert self.n.normalize_by_type("  hi  ", "str") == "hi"

    def test_normalize_by_type_int(self):
        assert self.n.normalize_by_type("123", "int") == 123

    # ---- 正则 ----
    def test_regex_extract(self):
        result = self.n.regex_extract("邮箱: test@example.com", r'[\w.]+@\w+\.\w+')
        assert "test@example.com" in result

    def test_regex_clean_json(self):
        dirty = "{'name': 'test', 'value': 123,}"  # 单引号+尾逗号
        cleaned = self.n.regex_clean_json(dirty)
        assert '"name"' in cleaned
        assert cleaned.endswith("}")


# ============================
# OutputSchema 测试
# ============================
class TestOutputSchema:
    """输出Schema测试"""

    def test_create_default(self):
        schema = OutputSchema("test", "1.0")
        assert schema.schema_name == "test"
        assert schema.version == "1.0"
        assert len(schema.fields) == 0

    def test_add_field(self):
        schema = OutputSchema("test")
        schema.add_field(FieldRule(
            target_key="name",
            source_keys=["name", "title"],
            required=True,
            default="",
            field_type="str",
        ))
        assert "name" in schema.fields
        assert schema.fields["name"].required is True
        assert "title" in schema.fields["name"].source_keys

    def test_add_fields_batch(self):
        schema = OutputSchema("test")
        schema.add_fields_batch([
            {"target_key": "a", "required": True, "default": ""},
            {"target_key": "b", "required": False, "default": 0},
        ])
        assert len(schema.fields) == 2
        assert schema.get_required_fields() == ["a"]

    def test_get_output_template(self):
        schema = OutputSchema("test")
        schema.add_fields_batch([
            {"target_key": "x", "default": "default_x"},
            {"target_key": "y", "default": 42},
        ])
        template = schema.get_output_template()
        assert template == {"x": "default_x", "y": 42}
        # 修改模板不应影响原schema
        template["x"] = "modified"
        assert schema.get_output_template()["x"] == "default_x"

    def test_generic_schema(self):
        schema = OutputSchema.create_generic_schema()
        assert "doc_id" in schema.fields
        assert "title" in schema.fields
        assert "entities" in schema.fields
        assert schema.fields["doc_id"].required is True
        assert len(schema.fields) >= 8

    def test_to_dict_and_from_dict(self):
        schema = OutputSchema("roundtrip", "2.0")
        schema.add_field(FieldRule(target_key="test", required=True, default=""))
        data = schema.to_dict()
        assert data["schema_name"] == "roundtrip"

        restored = OutputSchema.from_dict(data)
        assert restored.schema_name == "roundtrip"
        assert restored.version == "2.0"
        assert restored.fields["test"].required is True


# ============================
# Converter 测试
# ============================
class TestConverter:
    """转换器测试"""

    def setup_method(self):
        schema = OutputSchema("test_extraction", "1.0")
        schema.add_fields_batch([
            {"target_key": "title", "source_keys": ["title", "name"], "required": True, "default": "未命名", "field_type": "str"},
            {"target_key": "content_type", "source_keys": ["type", "content_type"], "required": False, "default": "document", "field_type": "str"},
            {"target_key": "author", "source_keys": ["author", "creator"], "required": False, "default": "", "field_type": "str"},
            {"target_key": "tags", "source_keys": ["tags", "keywords"], "required": False, "default": [], "field_type": "list"},
        ])
        self.converter = Converter(schema)

    def test_convert_one_basic(self):
        raw = {"title": "测试文档", "type": "report", "author": "张三"}
        output = self.converter.convert_one(raw)
        assert output["title"] == "测试文档"
        assert output["content_type"] == "report"
        assert output["author"] == "张三"

    def test_convert_one_default_value(self):
        raw = {}  # 完全空数据
        output = self.converter.convert_one(raw)
        assert output["title"] == "未命名"  # 必填字段默认值
        assert output["content_type"] == "document"

    def test_convert_one_source_key_priority(self):
        """测试source_keys优先级匹配"""
        raw = {"name": "从name取", "title": "从title取"}
        output = self.converter.convert_one(raw)
        # title的来源 keys 是 ["title", "name"]，优先匹配title
        assert output["title"] == "从title取"

    def test_convert_one_source_key_fallback(self):
        """测试source_keys回退匹配"""
        raw = {"name": "只有name字段"}
        output = self.converter.convert_one(raw)
        assert output["title"] == "只有name字段"

    def test_convert_one_case_insensitive(self):
        """测试大小写不敏感匹配"""
        raw = {"Title": "大写标题"}
        output = self.converter.convert_one(raw)
        assert output["title"] == "大写标题"

    def test_convert_one_with_custom_normalizer(self):
        """测试自定义规范化器"""
        schema = OutputSchema("custom_test")
        schema.add_field(FieldRule(
            target_key="clean_title",
            source_keys=["title"],
            default="",
            normalizers=[FieldNormalizer.trim, FieldNormalizer.to_lower],
        ))
        c = Converter(schema)
        output = c.convert_one({"title": "  HELLO WORLD  "})
        assert output["clean_title"] == "hello world"

    def test_convert_one_with_validator(self):
        """测试自定义校验器"""
        schema = OutputSchema("validate_test")
        schema.add_field(FieldRule(
            target_key="age",
            source_keys=["age"],
            default=0,
            validators=[lambda v: v > 0 and v < 150],
        ))
        c = Converter(schema)
        # 校验失败不应阻断，只记录warning
        output = c.convert_one({"age": -1})
        assert output["age"] == -1  # 值保持不变

    def test_convert_one_strict_mode(self):
        """测试严格模式"""
        schema = OutputSchema("strict_test")
        schema.add_field(FieldRule(target_key="title", required=True, default=None))
        c = Converter(schema)
        with pytest.raises(ValueError, match="缺少必填字段"):
            c.convert_one({}, strict=True)

    def test_convert_batch(self):
        raw_list = [
            {"title": "文档A", "author": "用户1"},
            {"title": "文档B", "author": "用户2"},
            {"title": "文档C"},
        ]
        results = self.converter.convert_batch(raw_list)
        assert len(results) == 3
        assert results[1]["author"] == "用户2"
        assert results[2]["author"] == ""

    def test_convert_llm_response_success(self):
        llm_result = {
            "success": True,
            "data": {"title": "LLM提取结果", "type": "article", "tags": ["AI", "NLP"]},
            "content_md5": "abc123",
        }
        output = self.converter.convert_llm_response(
            llm_result, doc_id="doc_001", source_file="/test.txt"
        )
        assert output["title"] == "LLM提取结果"
        assert output["tags"] == ["AI", "NLP"]

    def test_convert_llm_response_failure(self):
        llm_result = {
            "success": False,
            "error": "API调用失败",
        }
        output = self.converter.convert_llm_response(llm_result)
        assert "_extraction_error" in output

    # ---- 输出格式化 ----
    def test_to_json(self):
        data = {"title": "测试", "tags": ["a", "b"]}
        json_str = self.converter.to_json(data)
        parsed = json.loads(json_str)
        assert parsed["title"] == "测试"

    def test_to_jsonl(self):
        data_list = [
            {"title": "A", "author": "1"},
            {"title": "B", "author": "2"},
        ]
        jsonl_str = self.converter.to_jsonl(data_list)
        lines = jsonl_str.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["title"] == "A"

    def test_save_json(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "output.json")
            self.converter.save_json([{"a": 1}], path)
            with open(path, "r") as f:
                data = json.load(f)
            assert data[0]["a"] == 1
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_save_jsonl(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "output.jsonl")
            self.converter.save_jsonl([{"a": 1}, {"b": 2}], path)
            with open(path, "r") as f:
                lines = f.read().strip().split("\n")
            assert len(lines) == 2
        finally:
            import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_get_stats(self):
        stats = self.converter.get_stats()
        assert "field_count" in stats
        assert "schema_name" in stats

    def test_global_converter(self):
        assert isinstance(converter, Converter)
        # 全局converter使用通用Schema
        assert "doc_id" in converter.schema.fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
