# -*- coding: utf-8 -*-
"""
内置示例插件
提供常用清洗规则、通用Prompt模板等开箱即用的插件
"""
import re
from typing import Any, Dict, List

from .base_plugin import (
    ExtractionPromptPlugin,
    CleanRulePlugin,
    DocParserPlugin,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


# ============================
# 内置清洗规则插件
# ============================

class WhitespaceNormalizerPlugin(CleanRulePlugin):
    """空白字符规范化插件"""

    plugin_name = "whitespace_normalizer"
    plugin_version = "1.0"
    plugin_description = "统一处理文本中的空白字符、换行符、制表符等"
    plugin_author = "AI-DocAgent"

    def clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = data.copy()
        # 对字符串值进行空白规范化
        for key, value in cleaned.items():
            if isinstance(value, str):
                value = re.sub(r'[ \t]+', ' ', value)
                value = re.sub(r'\n{3,}', '\n\n', value)
                cleaned[key] = value.strip()
        return cleaned


class URLNormalizerPlugin(CleanRulePlugin):
    """URL清洗插件"""

    plugin_name = "url_normalizer"
    plugin_version = "1.0"
    plugin_description = "移除URL中的追踪参数（utm_*, fbclid等）"
    plugin_author = "AI-DocAgent"

    # 常见的跟踪参数
    TRACKING_PARAMS = [
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "gclsrc", "dclid", "msclkid",
        "_ga", "_gl", "_branch_match_id",
    ]

    def clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        cleaned = data.copy()
        for key, value in cleaned.items():
            if isinstance(value, str) and value.startswith("http"):
                try:
                    parsed = urlparse(value)
                    query_params = parse_qs(parsed.query, keep_blank_values=True)
                    # 移除追踪参数
                    filtered_params = {
                        k: v for k, v in query_params.items()
                        if k not in self.TRACKING_PARAMS
                    }
                    new_query = urlencode(filtered_params, doseq=True)
                    cleaned_url = urlunparse((
                        parsed.scheme, parsed.netloc, parsed.path,
                        parsed.params, new_query, parsed.fragment,
                    ))
                    cleaned[key] = cleaned_url
                except Exception:
                    pass
        return cleaned


class HTMLTagStripperPlugin(CleanRulePlugin):
    """HTML标签清除插件"""

    plugin_name = "html_tag_stripper"
    plugin_version = "1.0"
    plugin_description = "清除文本中残留的HTML标签"
    plugin_author = "AI-DocAgent"

    def clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = data.copy()
        for key, value in cleaned.items():
            if isinstance(value, str):
                cleaned[key] = re.sub(r'<[^>]+>', '', value).strip()
        return cleaned


class SensitiveDataMaskerPlugin(CleanRulePlugin):
    """敏感数据脱敏插件"""

    plugin_name = "sensitive_data_masker"
    plugin_version = "1.0"
    plugin_description = "对常见敏感信息（手机号、身份证、邮箱）进行脱敏处理"
    plugin_author = "AI-DocAgent"

    def clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = data.copy()
        for key, value in cleaned.items():
            if not isinstance(value, str):
                continue
            # 手机号脱敏 (保留前3后4)
            value = re.sub(
                r'(1[3-9]\d)\d{4}(\d{4})',
                r'\1****\2', value
            )
            # 身份证脱敏 (保留前6后4)
            value = re.sub(
                r'(\d{6})\d{8,11}(\d{4})',
                r'\1********\2', value
            )
            # 邮箱脱敏 (保留首字母和域名)
            value = re.sub(
                r'(\w)[\w.]*(@\w+\.\w+)',
                r'\1***\2', value
            )
            cleaned[key] = value
        return cleaned


# ============================
# 内置Prompt模板插件
# ============================

class GenericEntityExtractionPrompt(ExtractionPromptPlugin):
    """通用实体抽取Prompt"""

    plugin_name = "generic_entity_extraction"
    plugin_version = "1.0"
    plugin_description = "通用命名实体识别（NER）抽取Prompt"
    plugin_author = "AI-DocAgent"

    def get_prompt_template(self) -> str:
        return """请从以下文本中提取所有命名实体，按类别分类。

## 文本
{text}

## 输出格式
严格按JSON格式输出：
```json
{
    "persons": ["人名列表"],
    "organizations": ["组织机构列表"],
    "locations": ["地点列表"],
    "dates": ["日期列表"],
    "numbers": ["关键数值"],
    "other": ["其他实体"]
}
```
仅输出JSON，不要添加解释。"""

    def get_system_prompt(self) -> str:
        return "你是一个专业的命名实体识别系统。请精确提取文本中的各类实体。"


class KeyValueExtractionPrompt(ExtractionPromptPlugin):
    """键值对抽取Prompt"""

    plugin_name = "key_value_extraction"
    plugin_version = "1.0"
    plugin_description = "从非结构化文本中提取键值对结构化信息"
    plugin_author = "AI-DocAgent"

    def get_prompt_template(self) -> str:
        return """请从以下文本中提取所有结构化的键值对信息。

## 文本
{text}

## 要求
1. 提取所有明确的属性-值对
2. 键名使用英文snake_case
3. 值为null的字段不要输出
4. 多个同类值使用列表

## 输出格式
仅输出JSON对象。"""

    def get_system_prompt(self) -> str:
        return "你是一个数据抽取专家。请从文本中精确提取键值对信息。"


class SummaryGenerationPrompt(ExtractionPromptPlugin):
    """摘要生成Prompt"""

    plugin_name = "summary_generation"
    plugin_version = "1.0"
    plugin_description = "生成文本摘要"
    plugin_author = "AI-DocAgent"

    def get_prompt_template(self) -> str:
        return """请为以下文本生成简洁摘要。

## 文本
{text}

## 要求
1. 摘要长度不超过原文的30%
2. 保留关键事实和数据
3. 语言简洁准确

## 输出格式
```json
{
    "summary": "摘要内容",
    "key_points": ["要点1", "要点2", ...],
    "word_count_original": 原文词数,
    "word_count_summary": 摘要词数
}
```"""

    def get_system_prompt(self) -> str:
        return "你是一个专业的文本摘要生成系统。"


# ============================
# 内置文档解析插件示例
# ============================

class CSVTableParserPlugin(DocParserPlugin):
    """CSV表格解析插件（示例）"""

    plugin_name = "csv_table_parser"
    plugin_version = "1.0"
    plugin_description = "解析CSV文件为结构化表格数据"
    plugin_author = "AI-DocAgent"
    supported_extensions = ["csv", "tsv"]

    def parse(self, file_path: str, **kwargs) -> Dict[str, Any]:
        import csv

        delimiter = kwargs.get("delimiter", "," if file_path.endswith(".csv") else "\t")
        encoding = kwargs.get("encoding", "utf-8")

        rows = []
        with open(file_path, "r", encoding=encoding) as f:
            reader = csv.reader(f, delimiter=delimiter)
            for row in reader:
                rows.append(row)

        if not rows:
            return {"text": "", "paragraphs": [], "metadata": {"rows": 0}}

        # 尝试将第一行作为表头
        headers = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []

        # 构建结构化数据
        records = []
        for row in data_rows:
            record = {}
            for i, header in enumerate(headers):
                if i < len(row):
                    record[header.strip()] = row[i].strip()
            records.append(record)

        text_parts = [",".join(row) for row in rows]

        return {
            "text": "\n".join(text_parts),
            "paragraphs": text_parts,
            "records": records,
            "metadata": {
                "headers": headers,
                "total_rows": len(rows),
                "data_rows": len(data_rows),
            },
        }
