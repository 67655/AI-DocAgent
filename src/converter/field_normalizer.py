# -*- coding: utf-8 -*-
"""
字段规范化器
提供各种字段值清洗、类型转换、格式化函数
"""
import re
from datetime import datetime
from typing import Any, List, Optional


class FieldNormalizer:
    """字段值规范化工具集"""

    # ============================
    # 字符串规范化
    # ============================
    @staticmethod
    def trim(value: Any) -> str:
        """去除首尾空白"""
        return str(value).strip() if value is not None else ""

    @staticmethod
    def normalize_whitespace(value: Any) -> str:
        """合并多余空白字符"""
        text = str(value) if value is not None else ""
        text = re.sub(r'[ \t]+', ' ', text)     # 合并空格和制表符
        text = re.sub(r'\n{3,}', '\n\n', text)   # 最多保留双换行
        return text.strip()

    @staticmethod
    def remove_html_tags(value: Any) -> str:
        """移除HTML标签"""
        text = str(value) if value is not None else ""
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def truncate(value: Any, max_length: int = 1000) -> str:
        """截断过长文本"""
        text = str(value) if value is not None else ""
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    @staticmethod
    def to_lower(value: Any) -> str:
        """转小写"""
        return str(value).lower() if value is not None else ""

    # ============================
    # 数值规范化
    # ============================
    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        """安全转换为整数"""
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def to_float(value: Any, default: float = 0.0) -> float:
        """安全转换为浮点数"""
        try:
            return float(str(value).strip())
        except (ValueError, TypeError):
            return default

    @staticmethod
    def extract_number(value: Any) -> Optional[float]:
        """从文本中提取第一个数字"""
        if value is None:
            return None
        match = re.search(r'[-+]?\d+\.?\d*', str(value))
        if match:
            return float(match.group())
        return None

    # ============================
    # 列表规范化
    # ============================
    @staticmethod
    def to_list(value: Any, separator: str = ",") -> list:
        """
        将各种格式转为列表
        支持：列表、逗号分隔字符串、分号分隔字符串、换行分隔
        """
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (set, tuple)):
            return list(value)

        text = str(value).strip()
        if not text:
            return []

        # 尝试按常见分隔符拆分
        for sep in [separator, ";", "\n", "|", "、", "，", "；"]:
            if sep in text:
                return [item.strip() for item in text.split(sep) if item.strip()]

        return [text]

    @staticmethod
    def deduplicate_list(items: list) -> list:
        """列表去重（保持顺序）"""
        seen = set()
        result = []
        for item in items:
            key = str(item) if not isinstance(item, (int, float)) else item
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    # ============================
    # 日期时间规范化
    # ============================
    @staticmethod
    def to_iso_datetime(value: Any) -> str:
        """
        尝试将各种日期格式转为ISO 8601
        """
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()

        text = str(value).strip()
        # 尝试常见日期格式
        formats = [
            ("%Y-%m-%dT%H:%M:%S", None),
            ("%Y-%m-%d %H:%M:%S", None),
            ("%Y-%m-%d", None),
            ("%Y/%m/%d", None),
            ("%Y年%m月%d日", None),
            # 带额外字符的ISO格式
            (r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", "regex"),
        ]

        for fmt, mode in formats:
            if mode == "regex":
                match = re.search(fmt, text)
                if match:
                    return match.group(1)
            else:
                try:
                    return datetime.strptime(text[:len(fmt)], fmt).isoformat()
                except (ValueError, IndexError):
                    continue

        return text

    # ============================
    # 通用值规范化
    # ============================
    @staticmethod
    def normalize_by_type(value: Any, target_type: Optional[str]) -> Any:
        """
        根据目标类型自动规范化值

        Args:
            value: 原始值
            target_type: 目标类型 (str/int/float/bool/list/dict)

        Returns:
            规范化后的值
        """
        if value is None:
            return None

        type_map = {
            "str": lambda v: FieldNormalizer.trim(v),
            "int": lambda v: FieldNormalizer.to_int(v),
            "float": lambda v: FieldNormalizer.to_float(v),
            "bool": lambda v: bool(v) if not isinstance(v, bool) else v,
            "list": lambda v: FieldNormalizer.to_list(v) if not isinstance(v, list) else v,
            "dict": lambda v: v if isinstance(v, dict) else {},
        }
        if target_type and target_type in type_map:
            return type_map[target_type](value)
        return value

    # ============================
    # 正则清洗
    # ============================
    @staticmethod
    def regex_extract(value: Any, pattern: str, group: int = 0) -> Optional[str]:
        """用正则提取值"""
        if value is None:
            return None
        match = re.search(pattern, str(value))
        if match:
            return match.group(group)
        return None

    @staticmethod
    def regex_replace(value: Any, pattern: str, replacement: str = "") -> str:
        """正则替换"""
        if value is None:
            return ""
        return re.sub(pattern, replacement, str(value))

    @staticmethod
    def regex_clean_json(value: Any) -> str:
        """
        清洗LLM输出的不规则JSON文本
        修复常见问题：多余逗号、非标准引号、注释等
        """
        text = str(value) if value is not None else ""
        # 移除JSON注释 (// ...)
        text = re.sub(r'//.*?\n', '\n', text)
        # 移除块注释 (/* ... */)
        text = re.sub(r'/\*[\s\S]*?\*/', '', text)
        # 修复中文引号
        text = text.replace('“', '"').replace('”', '"')
        text = text.replace('‘', "'").replace('’', "'")
        # 移除尾部逗号（在 ] 或 } 之前）
        text = re.sub(r',\s*([}\]])', r'\1', text)
        # 修复单引号JSON（转为双引号，注意处理内部双引号）
        # 简单场景：整段单引号JSON转双引号
        if text.startswith("{'") or text.startswith("[{"):
            text = text.replace("'", '"')
        return text.strip()
