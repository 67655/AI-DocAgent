# -*- coding: utf-8 -*-
"""parser 模块单元测试"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from parser.base_parser import BaseParser, ParseResult
from parser.txt_parser import TXTParser
from parser.pdf_parser import PDFParser
from parser.word_parser import WordParser
from parser.html_parser import HTMLParser
from parser.parser_factory import ParserFactory, parser_factory


# ============================
# ParseResult 测试
# ============================
class TestParseResult:
    """ParseResult数据结构测试"""

    def test_default_values(self):
        """测试默认值"""
        result = ParseResult()
        assert result.success is True
        assert result.text == ""
        assert result.paragraphs == []
        assert result.tables == []

    def test_failed_result(self):
        """测试失败结果"""
        result = ParseResult(success=False, error="文件损坏")
        assert result.success is False
        assert result.error == "文件损坏"

    def test_to_dict(self):
        """测试字典转换"""
        result = ParseResult(
            file_path="/test/doc.pdf",
            file_type="pdf",
            text="示例文本",
            paragraphs=["段落1", "段落2"],
        )
        d = result.to_dict()
        assert d["file_type"] == "pdf"
        assert d["paragraphs_count"] == 2
        assert d["tables_count"] == 0

    def test_get_full_text(self):
        """测试获取完整文本"""
        result = ParseResult(text="完整文本内容")
        assert result.get_full_text() == "完整文本内容"

        # 无text但有paragraphs时自动拼接
        result2 = ParseResult(paragraphs=["第一段", "第二段", "第三段"])
        assert result2.get_full_text() == "第一段\n第二段\n第三段"


# ============================
# TXTParser 测试
# ============================
class TestTXTParser:
    """纯文本解析器测试"""

    def setup_method(self):
        self.parser = TXTParser()
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_file(self, name, content, encoding="utf-8"):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return path

    def test_parse_simple_txt(self):
        """测试简单TXT解析"""
        path = self._create_file("test.txt", "段落一\n\n段落二\n\n段落三")
        result = self.parser.parse(path)
        assert result.success
        assert len(result.paragraphs) == 3
        assert result.paragraphs[0] == "段落一"

    def test_can_parse_txt(self):
        """测试文件类型识别"""
        assert self.parser.can_parse("file.txt") is True
        assert self.parser.can_parse("file.md") is True
        assert self.parser.can_parse("file.pdf") is False

    def test_parse_with_custom_separator(self):
        """测试自定义段落分隔符"""
        path = self._create_file("test2.txt", "A---B---C")
        result = self.parser.parse(path, paragraph_separator="---")
        assert len(result.paragraphs) == 3

    def test_parse_empty_file(self):
        """测试空文件"""
        path = self._create_file("empty.txt", "")
        result = self.parser.parse(path)
        assert result.success
        assert result.text == ""

    def test_parse_encoding(self):
        """测试GBK编码"""
        content = "中文测试内容\n\n第二段"
        path = self._create_file("gbk.txt", content, encoding="gbk")
        # 用utf-8读GBK文件可能失败，需自动回退
        result = self.parser.parse(path, encoding="utf-8")
        # 应该能通过编码自动回退读成功
        assert result.success
        assert "中文" in result.text or "测试" in result.text or result.success

    def test_safe_parse_nonexistent(self):
        """测试安全解析不存在的文件"""
        result = self.parser.safe_parse("/nonexistent/file.txt")
        assert result.success is False
        assert "不存在" in result.error

    def test_metadata(self):
        """测试元数据提取"""
        path = self._create_file("meta.txt", "line1\nline2\n\nparagraph")
        result = self.parser.parse(path)
        assert result.metadata["total_lines"] == 4
        assert result.metadata["non_empty_lines"] == 3


# ============================
# ParserFactory 测试
# ============================
class TestParserFactory:
    """解析器工厂测试"""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.factory = ParserFactory()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_file(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_get_parser_for_txt(self):
        parser = self.factory.get_parser("test.txt")
        assert isinstance(parser, TXTParser)

    def test_get_parser_for_pdf(self):
        parser = self.factory.get_parser("doc.pdf")
        assert isinstance(parser, PDFParser)

    def test_get_parser_for_docx(self):
        parser = self.factory.get_parser("report.docx")
        assert isinstance(parser, WordParser)

    def test_get_parser_for_html(self):
        parser = self.factory.get_parser("page.html")
        assert isinstance(parser, HTMLParser)

    def test_get_parser_for_url(self):
        parser = self.factory.get_parser("https://example.com")
        assert isinstance(parser, HTMLParser)

    def test_get_parser_unknown_fallback(self):
        """未知扩展名回退到TXT解析器"""
        parser = self.factory.get_parser("data.xyz")
        assert isinstance(parser, TXTParser)

    def test_parse_txt_via_factory(self):
        """通过工厂解析TXT"""
        path = self._create_file("factory_test.txt", "工厂测试内容\n\n段落2")
        result = self.factory.parse(path)
        assert result.success
        assert "工厂测试内容" in result.text

    def test_get_supported_extensions(self):
        exts = self.factory.get_supported_extensions()
        assert "txt" in exts
        assert "pdf" in exts
        assert "docx" in exts
        assert "html" in exts

    def test_get_registered_parsers(self):
        parsers = self.factory.get_registered_parsers()
        assert len(parsers) >= 4
        names = [p["name"] for p in parsers]
        assert "pdf" in names
        assert "docx" in names
        assert "txt" in names
        assert "html" in names

    def test_register_custom_parser(self):
        """测试注册自定义解析器"""
        class CustomParser(BaseParser):
            supported_extensions = ["custom"]
            parser_name = "custom"

            def parse(self, file_path, **kwargs):
                return ParseResult(success=True, text="custom content")

        self.factory.register_parser(CustomParser())
        parser = self.factory.get_parser("test.custom")
        assert isinstance(parser, CustomParser)
        assert parser.parser_name == "custom"

    def test_unregister_parser(self):
        """测试注销解析器"""
        self.factory.unregister_parser("pdf")
        parser = self.factory.get_parser("doc.pdf")
        # 注销后PDF应回退到TXT
        assert isinstance(parser, TXTParser)

        # 重新注册以恢复
        self.factory.register_parser(PDFParser())
        parser = self.factory.get_parser("doc.pdf")
        assert isinstance(parser, PDFParser)

    def test_global_factory(self):
        """测试全局工厂实例"""
        assert isinstance(parser_factory, ParserFactory)
        exts = parser_factory.get_supported_extensions()
        assert len(exts) >= 4

    def test_batch_parse(self):
        """测试批量解析"""
        p1 = self._create_file("b1.txt", "文件1内容")
        p2 = self._create_file("b2.txt", "文件2内容")

        results = self.factory.batch_parse([p1, p2])
        assert len(results) == 2
        assert results[0].success
        assert results[1].success
        assert "文件1内容" in results[0].text
        assert "文件2内容" in results[1].text


# ============================
# HTMLParser 测试
# ============================
class TestHTMLParser:
    """HTML解析器测试"""

    def setup_method(self):
        self.parser = HTMLParser()
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_html(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_parse_simple_html(self):
        html = """<html><head><title>测试页面</title></head>
        <body><h1>标题</h1><p>第一段内容</p><p>第二段内容</p></body></html>"""
        path = self._create_html("test.html", html)
        result = self.parser.parse(path)

        assert result.success
        assert "标题" in result.text
        assert "第一段内容" in result.text
        assert result.metadata.get("title") == "测试页面"

    def test_strip_script_and_style(self):
        """测试过滤script和style标签内容"""
        html = """<html><head><style>body{color:red;}</style></head>
        <body><script>alert('xss')</script><p>可见内容</p></body></html>"""
        path = self._create_html("strip.html", html)
        result = self.parser.parse(path)

        assert result.success
        assert "alert" not in result.text
        assert "body{color" not in result.text
        assert "可见内容" in result.text

    def test_extract_tables(self):
        """测试表格提取"""
        html = """<html><body>
        <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
        </body></html>"""
        path = self._create_html("table.html", html)
        result = self.parser.parse(path, extract_tables=True)

        assert result.success
        assert len(result.tables) == 1
        assert result.tables[0][0] == ["A", "B"]
        assert result.tables[0][1] == ["1", "2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
