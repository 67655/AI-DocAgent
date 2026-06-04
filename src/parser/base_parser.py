# -*- coding: utf-8 -*-
"""
文档解析基类
定义统一的解析接口，所有具体解析器必须继承此基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParseResult:
    """解析结果统一数据结构"""
    success: bool = True
    file_path: str = ""
    file_type: str = ""
    file_size: int = 0

    # 解析出的内容
    text: str = ""                          # 正文纯文本
    paragraphs: List[str] = field(default_factory=list)  # 段落列表
    tables: List[List[List[str]]] = field(default_factory=list)  # 表格数据 [表格][行][列]
    images: List[Dict] = field(default_factory=list)     # 图片元信息
    metadata: Dict[str, Any] = field(default_factory=dict)  # 文档元数据

    # 错误信息
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "text": self.text,
            "paragraphs_count": len(self.paragraphs),
            "tables_count": len(self.tables),
            "images_count": len(self.images),
            "metadata": self.metadata,
            "error": self.error,
        }

    def get_full_text(self) -> str:
        """获取完整文本内容（段落拼接）"""
        if self.text:
            return self.text
        return "\n".join(self.paragraphs)


class BaseParser(ABC):
    """文档解析器抽象基类"""

    # 子类需定义的属性
    supported_extensions: List[str] = []     # 支持的文件扩展名
    parser_name: str = "base"                # 解析器名称

    def can_parse(self, file_path: str) -> bool:
        """
        判断是否能解析指定文件

        Args:
            file_path: 文件路径

        Returns:
            是否能解析
        """
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        return ext in self.supported_extensions or ext == file_path.lower()

    @abstractmethod
    def parse(self, file_path: str, **kwargs) -> ParseResult:
        """
        解析文档文件

        Args:
            file_path: 文件路径
            **kwargs: 解析器特定参数

        Returns:
            ParseResult 统一解析结果
        """
        pass

    def safe_parse(self, file_path: str, **kwargs) -> ParseResult:
        """
        安全的解析方法（内置异常捕获）

        Args:
            file_path: 文件路径
            **kwargs: 解析器特定参数

        Returns:
            ParseResult，异常时 success=False
        """
        import os
        try:
            if not os.path.exists(file_path):
                return ParseResult(
                    success=False,
                    file_path=file_path,
                    error=f"文件不存在: {file_path}",
                )
            result = self.parse(file_path, **kwargs)
            result.file_path = file_path
            result.file_size = os.path.getsize(file_path)
            return result
        except Exception as e:
            from ..utils.logger import get_logger
            logger = get_logger(__name__)
            logger.error(f"解析失败 [{self.parser_name}]: {file_path} | {e}")
            return ParseResult(
                success=False,
                file_path=file_path,
                file_type=self.parser_name,
                error=f"{type(e).__name__}: {str(e)}",
            )
