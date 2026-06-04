# -*- coding: utf-8 -*-
"""
PDF文档解析器
基于 PyPDF2 实现文本提取
"""
import os
from typing import Optional

from .base_parser import BaseParser, ParseResult
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PDFParser(BaseParser):
    """PDF文档解析器"""

    supported_extensions = ["pdf"]
    parser_name = "pdf"

    def parse(self, file_path: str, **kwargs) -> ParseResult:
        """
        解析PDF文件，提取文本内容

        Args:
            file_path: PDF文件路径
            **kwargs:
                extract_metadata: 是否提取元数据（默认True）
                page_range: 页码范围 (start, end)，默认全部
                password: PDF密码（可选）

        Returns:
            ParseResult
        """
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return ParseResult(
                success=False,
                file_path=file_path,
                file_type=self.parser_name,
                error="PyPDF2未安装，请执行: pip install PyPDF2",
            )

        password = kwargs.get("password", None)
        page_range = kwargs.get("page_range", None)
        extract_meta = kwargs.get("extract_metadata", True)

        reader = PdfReader(file_path)

        # 处理加密PDF
        if reader.is_encrypted:
            if not password:
                return ParseResult(
                    success=False,
                    file_path=file_path,
                    file_type=self.parser_name,
                    error="PDF文件已加密，需要提供密码",
                )
            result = reader.decrypt(password)
            if result == 0:
                return ParseResult(
                    success=False,
                    file_path=file_path,
                    file_type=self.parser_name,
                    error="PDF密码错误",
                )

        total_pages = len(reader.pages)

        # 确定页码范围
        if page_range:
            start, end = page_range
            start = max(0, start)
            end = min(total_pages, end)
        else:
            start, end = 0, total_pages

        # 逐页提取文本
        paragraphs = []
        full_text_parts = []

        for page_num in range(start, end):
            page = reader.pages[page_num]
            page_text = page.extract_text()
            if page_text and page_text.strip():
                full_text_parts.append(page_text.strip())
                # 按双换行拆分段落
                page_paragraphs = [
                    p.strip() for p in page_text.strip().split("\n\n")
                    if p.strip()
                ]
                paragraphs.extend(page_paragraphs)

        full_text = "\n\n".join(full_text_parts)

        # 提取元数据
        metadata = {}
        if extract_meta and reader.metadata:
            for key, value in reader.metadata.items():
                if value:
                    clean_key = key.lstrip("/") if key.startswith("/") else key
                    metadata[clean_key] = str(value)

        metadata.update({
            "total_pages": total_pages,
            "parsed_pages": f"{start}-{end - 1}",
            "page_count": end - start,
        })

        logger.info(f"PDF解析完成: {file_path} | {end - start}/{total_pages}页")

        return ParseResult(
            success=True,
            file_path=file_path,
            file_type=self.parser_name,
            text=full_text,
            paragraphs=paragraphs,
            metadata=metadata,
        )

    def parse_page_by_page(self, file_path: str, **kwargs) -> list:
        """
        逐页解析PDF，返回每页的ParseResult列表
        适用于大文件分页处理场景

        Args:
            file_path: PDF文件路径
            **kwargs: 同 parse()

        Returns:
            [ParseResult, ...] 每页一个结果
        """
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return [ParseResult(success=False, error="PyPDF2未安装")]

        password = kwargs.get("password", None)
        reader = PdfReader(file_path)

        if reader.is_encrypted:
            if not password or reader.decrypt(password) == 0:
                return [ParseResult(success=False, error="PDF解密失败")]

        results = []
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            text = page_text.strip() if page_text else ""
            paras = [
                p.strip() for p in text.split("\n\n") if p.strip()
            ] if text else []

            results.append(ParseResult(
                success=True,
                file_path=f"{file_path}#page{page_num + 1}",
                file_type="pdf_page",
                text=text,
                paragraphs=paras,
                metadata={"page_number": page_num + 1, "total_pages": len(reader.pages)},
            ))

        return results
