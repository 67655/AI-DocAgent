# -*- coding: utf-8 -*-
"""
纯文本文档解析器
支持 TXT / Markdown / JSON / JSONL 等纯文本格式
"""
from typing import Optional

from .base_parser import BaseParser, ParseResult
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TXTParser(BaseParser):
    """纯文本文档解析器"""

    supported_extensions = ["txt", "md", "markdown", "json", "jsonl", "csv", "log"]
    parser_name = "txt"

    def parse(self, file_path: str, **kwargs) -> ParseResult:
        """
        解析纯文本文件

        Args:
            file_path: 文本文件路径
            **kwargs:
                encoding: 文件编码（默认 utf-8）
                paragraph_separator: 段落分隔符（默认双换行 \n\n）
                skip_empty_lines: 是否跳过空行（默认True）

        Returns:
            ParseResult
        """
        encoding = kwargs.get("encoding", "utf-8")
        paragraph_sep = kwargs.get("paragraph_separator", "\n\n")
        skip_empty = kwargs.get("skip_empty_lines", True)

        # 尝试多种编码读取
        content = self._read_file(file_path, encoding)

        if content is None:
            return ParseResult(
                success=False,
                file_path=file_path,
                file_type=self.parser_name,
                error=f"无法读取文件，尝试编码: {encoding}",
            )

        # 按分隔符拆分段落
        raw_paragraphs = content.split(paragraph_sep)
        if skip_empty:
            paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]
        else:
            paragraphs = [p.strip() for p in raw_paragraphs]

        # 文本行信息
        lines = content.split("\n")
        non_empty_lines = [l for l in lines if l.strip()]

        metadata = {
            "encoding": encoding,
            "total_lines": len(lines),
            "non_empty_lines": len(non_empty_lines),
            "paragraphs_count": len(paragraphs),
            "char_count": len(content),
        }

        logger.info(f"TXT解析完成: {file_path} | {len(paragraphs)}段落, {len(lines)}行")

        return ParseResult(
            success=True,
            file_path=file_path,
            file_type=self.parser_name,
            text=content,
            paragraphs=paragraphs,
            metadata=metadata,
        )

    @staticmethod
    def _read_file(file_path: str, primary_encoding: str = "utf-8") -> Optional[str]:
        """
        读取文件内容，自动尝试多种编码

        Args:
            file_path: 文件路径
            primary_encoding: 首选编码

        Returns:
            文件内容字符串，失败返回None
        """
        # 按优先级尝试的编码列表
        encodings = [primary_encoding, "utf-8-sig", "gbk", "gb2312", "gb18030",
                     "latin-1", "cp1252", "iso-8859-1"]

        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                return None

        # 最后尝试二进制模式读取
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
                return raw.decode("utf-8", errors="replace")
        except Exception:
            return None
