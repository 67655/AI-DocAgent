# -*- coding: utf-8 -*-
"""
HTML网页文档解析器
基于 BeautifulSoup4 实现网页文本提取和清洗
"""
import re
from typing import Dict, List, Optional

from .base_parser import BaseParser, ParseResult
from ..utils.logger import get_logger

logger = get_logger(__name__)


class HTMLParser(BaseParser):
    """HTML网页文档解析器"""

    supported_extensions = ["html", "htm", "xhtml"]
    parser_name = "html"

    # 需要移除的标签（非内容标签）
    REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "aside",
                   "noscript", "iframe", "svg", "form", "button", "input"]

    def parse(self, file_path: str, **kwargs) -> ParseResult:
        """
        解析HTML文件或URL

        Args:
            file_path: HTML文件路径 或 网页URL
            **kwargs:
                is_url: 是否为URL（默认False，自动检测）
                encoding: 文件编码（默认自动检测）
                extract_tables: 是否提取表格（默认True）
                extract_links: 是否提取链接（默认False）
                extract_images: 是否提取图片信息（默认False）
                remove_tags: 额外需要移除的标签列表
                content_selector: CSS选择器，只提取指定区域内容

        Returns:
            ParseResult
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return ParseResult(
                success=False,
                file_path=file_path,
                file_type=self.parser_name,
                error="beautifulsoup4未安装，请执行: pip install beautifulsoup4",
            )

        is_url = kwargs.get("is_url", file_path.startswith("http"))

        # 获取HTML内容
        if is_url:
            html_content = self._fetch_url(file_path, **kwargs)
            if html_content is None:
                return ParseResult(
                    success=False,
                    file_path=file_path,
                    file_type=self.parser_name,
                    error="URL请求失败",
                )
        else:
            encoding = kwargs.get("encoding", "utf-8")
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    html_content = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")

        # 提取元数据
        metadata = self._extract_meta(soup)

        # 按选择器限定内容范围
        content_selector = kwargs.get("content_selector")
        if content_selector:
            content_root = soup.select_one(content_selector)
            if content_root:
                soup = content_root

        # 移除不需要的标签
        remove_tags = self.REMOVE_TAGS.copy()
        extra_remove = kwargs.get("remove_tags", [])
        remove_tags.extend(extra_remove)
        for tag in soup.find_all(remove_tags):
            tag.decompose()

        # 提取正文
        body = soup.find("body") or soup
        full_text = body.get_text(separator="\n", strip=True)

        # 清理文本
        # 合并多余空白行
        full_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', full_text)
        full_text = re.sub(r'[ \t]{2,}', ' ', full_text)

        # 拆分段落
        paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

        # 提取表格
        tables = []
        if kwargs.get("extract_tables", True):
            tables = self._extract_tables(soup)

        # 提取链接
        images = []
        if kwargs.get("extract_images", False):
            images = self._extract_images(soup, file_path if is_url else "")

        metadata["paragraphs_count"] = len(paragraphs)
        metadata["tables_count"] = len(tables)

        logger.info(f"HTML解析完成: {file_path} | {len(paragraphs)}段落")

        return ParseResult(
            success=True,
            file_path=file_path,
            file_type=self.parser_name,
            text=full_text,
            paragraphs=paragraphs,
            tables=tables,
            images=images,
            metadata=metadata,
        )

    def _fetch_url(self, url: str, **kwargs) -> Optional[str]:
        """通过HTTP获取网页内容"""
        try:
            from ..utils.http_client import HTTPClient

            client = HTTPClient(name="html_parser", timeout=15)
            response = client.get(url)
            # 自动检测编码
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
            return response.text
        except Exception as e:
            logger.error(f"URL请求失败: {url} | {e}")
            return None

    def _extract_meta(self, soup) -> Dict:
        """提取网页元数据"""
        meta = {}
        # title
        title_tag = soup.find("title")
        if title_tag:
            meta["title"] = title_tag.get_text(strip=True)

        # meta标签
        for tag in soup.find_all("meta"):
            name = tag.get("name", tag.get("property", ""))
            content = tag.get("content", "")
            if name and content:
                meta[name] = content

        return meta

    def _extract_tables(self, soup) -> List[List[List[str]]]:
        """提取HTML表格"""
        tables = []
        for table in soup.find_all("table"):
            table_data = []
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                row_data = [cell.get_text(strip=True) for cell in cells]
                if row_data:
                    table_data.append(row_data)
            if table_data:
                tables.append(table_data)
        return tables

    def _extract_images(self, soup, base_url: str = "") -> List[Dict]:
        """提取图片信息"""
        from urllib.parse import urljoin

        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "")
            if src:
                if base_url and not src.startswith("http"):
                    src = urljoin(base_url, src)
                images.append({"src": src, "alt": alt})
        return images
