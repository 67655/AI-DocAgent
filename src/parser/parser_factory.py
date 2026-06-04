# -*- coding: utf-8 -*-
"""
解析器工厂
根据文件扩展名自动选择合适的解析器
"""
from typing import Dict, List, Optional, Type

from .base_parser import BaseParser, ParseResult
from .pdf_parser import PDFParser
from .word_parser import WordParser
from .txt_parser import TXTParser
from .html_parser import HTMLParser
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ParserFactory:
    """
    解析器工厂类
    根据文件类型自动分发到对应的解析器
    """

    def __init__(self):
        """初始化，注册所有内置解析器"""
        self._parsers: Dict[str, BaseParser] = {}
        self._register_builtin_parsers()

    def _register_builtin_parsers(self):
        """注册所有内置解析器"""
        builtin: List[BaseParser] = [
            PDFParser(),
            WordParser(),
            TXTParser(),
            HTMLParser(),
        ]
        for parser in builtin:
            self.register_parser(parser)

    def register_parser(self, parser: BaseParser):
        """
        注册一个解析器（支持插件扩展）

        Args:
            parser: 解析器实例
        """
        for ext in parser.supported_extensions:
            self._parsers[ext.lower()] = parser
        logger.debug(f"注册解析器: {parser.parser_name} -> {parser.supported_extensions}")

    def unregister_parser(self, extension: str):
        """
        注销指定扩展名的解析器

        Args:
            extension: 文件扩展名
        """
        ext = extension.lower().lstrip(".")
        if ext in self._parsers:
            parser = self._parsers.pop(ext)
            logger.debug(f"注销解析器: {parser.parser_name} ({ext})")

    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        """
        根据文件路径获取对应的解析器

        Args:
            file_path: 文件路径或URL

        Returns:
            BaseParser 实例或 None
        """
        # 处理URL
        if file_path.startswith("http://") or file_path.startswith("https://"):
            return self._parsers.get("html")

        # 根据扩展名查找
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        parser = self._parsers.get(ext)

        if parser is None:
            # 尝试纯文本作为兜底
            parser = self._parsers.get("txt")

        return parser

    def parse(self, file_path: str, **kwargs) -> ParseResult:
        """
        自动选择解析器并解析文档（最常用入口）

        Args:
            file_path: 文件路径或URL
            **kwargs: 传递给具体解析器的参数

        Returns:
            ParseResult 统一解析结果
        """
        parser = self.get_parser(file_path)
        if parser is None:
            return ParseResult(
                success=False,
                file_path=file_path,
                error=f"不支持的文件格式: {file_path}",
            )
        return parser.safe_parse(file_path, **kwargs)

    def batch_parse(self, file_paths: List[str], **kwargs) -> List[ParseResult]:
        """
        批量解析多个文档

        Args:
            file_paths: 文件路径列表
            **kwargs: 传递给具体解析器的参数

        Returns:
            ParseResult 列表（与输入顺序一致）
        """
        results = []
        for path in file_paths:
            result = self.parse(path, **kwargs)
            results.append(result)
        return results

    def get_supported_extensions(self) -> List[str]:
        """获取所有支持的文件扩展名"""
        return sorted(self._parsers.keys())

    def get_registered_parsers(self) -> List[Dict]:
        """获取所有已注册的解析器信息"""
        seen = set()
        info = []
        for parser in self._parsers.values():
            if parser.parser_name not in seen:
                seen.add(parser.parser_name)
                info.append({
                    "name": parser.parser_name,
                    "extensions": parser.supported_extensions,
                })
        return info


# 全局解析器工厂实例
parser_factory = ParserFactory()
