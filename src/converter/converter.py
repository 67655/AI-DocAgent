# -*- coding: utf-8 -*-
"""
结构化转换引擎
将LLM抽取的原始数据转换为统一Schema的标准化JSON/JSONL输出
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional,Union

from .schema import OutputSchema, FieldRule
from .field_normalizer import FieldNormalizer
from ..utils.logger import get_logger
from ..utils.md5_utils import deduplicator

logger = get_logger(__name__)


class Converter:
    """
    结构化转换器
    将原始数据按Schema定义转换为标准化输出
    """

    def __init__(self, schema: Optional[OutputSchema] = None):
        """
        Args:
            schema: 输出Schema定义（None则使用通用Schema）
        """
        self.schema = schema or OutputSchema.create_generic_schema()
        self.normalizer = FieldNormalizer()
        self._conversion_count = 0

    def convert_one(self, raw_data: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
        """
        转换单条数据

        Args:
            raw_data: 原始数据字典（如LLM抽取结果）
            strict: 是否严格模式（缺少必填字段时抛异常）

        Returns:
            按Schema规范化的输出字典

        Raises:
            ValueError: 严格模式下缺少必填字段
        """
        output = self.schema.get_output_template()

        for target_key, rule in self.schema.fields.items():
            # 1. 从原始数据中匹配值（按source_keys优先级）
            value = self._match_value(raw_data, rule)

            # 2. 应用规范化管道
            value = self._normalize_value(value, rule)

            # 3. 必填检查
            if rule.required and (value is None or value == "" or value == []):
                if strict:
                    raise ValueError(f"缺少必填字段: {target_key}")
                value = rule.default

            output[target_key] = value

        # 自动补充时间戳
        if "extraction_time" in output and not output["extraction_time"]:
            output["extraction_time"] = datetime.now().isoformat()

        self._conversion_count += 1
        return output

    def convert_batch(self, raw_data_list: List[Dict[str, Any]], strict: bool = False) -> List[Dict[str, Any]]:
        """
        批量转换

        Args:
            raw_data_list: 原始数据列表
            strict: 是否严格模式

        Returns:
            标准化输出列表
        """
        results = []
        for raw in raw_data_list:
            try:
                converted = self.convert_one(raw, strict=strict)
                results.append(converted)
            except Exception as e:
                logger.error(f"转换失败: {e}")
                if strict:
                    raise
                # 非严格模式下记录错误并跳过
                results.append({
                    **self.schema.get_output_template(),
                    "doc_id": raw.get("doc_id", "error"),
                    "source_file": raw.get("source_file", ""),
                    "_conversion_error": str(e),
                })
        return results

    def convert_llm_response(
        self,
        llm_result: Dict[str, Any],
        doc_id: str = "",
        source_file: str = "",
    ) -> Dict[str, Any]:
        """
        将LLM抽取结果直接转换为标准格式（便捷方法）

        Args:
            llm_result: LLM抽取结果 {"success": bool, "data": dict, ...}
            doc_id: 文档ID
            source_file: 源文件路径

        Returns:
            标准化输出
        """
        if not llm_result.get("success"):
            return {
                **self.schema.get_output_template(),
                "doc_id": doc_id or "error",
                "source_file": source_file,
                "_extraction_error": llm_result.get("error", "unknown"),
            }

        raw_data = llm_result.get("data") or {}
        if not isinstance(raw_data, dict):
            raw_data = {"raw_text": str(raw_data)}

        # 补充元信息
        raw_data["doc_id"] = raw_data.get("doc_id") or doc_id
        raw_data["source_file"] = raw_data.get("source_file") or source_file
        raw_data["content_md5"] = llm_result.get("content_md5", "")

        return self.convert_one(raw_data)

    def _match_value(self, raw_data: Dict[str, Any], rule: FieldRule) -> Any:
        """
        从原始数据中按source_keys优先级匹配值

        Args:
            raw_data: 原始数据字典
            rule: 字段规则

        Returns:
            匹配到的值，未匹配返回None
        """
        for source_key in rule.source_keys:
            # 精确匹配
            if source_key in raw_data:
                return raw_data[source_key]
            # 大小写不敏感匹配
            for raw_key in raw_data:
                if raw_key.lower() == source_key.lower():
                    return raw_data[raw_key]
        return None

    def _normalize_value(self, value: Any, rule: FieldRule) -> Any:
        """
        对值应用规范化管道

        规范化顺序：
        1. 类型转换 (field_type)
        2. 通用规范化 (normalizers)
        3. 自定义校验 (validators) — 仅记录，不改变值

        Args:
            value: 原始值
            rule: 字段规则

        Returns:
            规范化后的值
        """
        # 空值处理
        if value is None:
            return rule.default

        # 类型规范化
        if rule.field_type:
            value = self.normalizer.normalize_by_type(value, rule.field_type)

        # 应用自定义规范化器
        for normalizer in rule.normalizers:
            try:
                value = normalizer(value)
            except Exception as e:
                logger.warning(f"规范化器执行失败 for {rule.target_key}: {e}")

        # 自定义校验器（记录但不阻断）
        for validator in rule.validators:
            try:
                if not validator(value):
                    logger.warning(f"字段 {rule.target_key} 校验未通过: {value}")
            except Exception as e:
                logger.warning(f"校验器执行异常 for {rule.target_key}: {e}")

        return value

    # ============================
    # 输出格式化
    # ============================
    def to_json(self, data: Union[Dict, List[Dict]], indent: int = 2, ensure_ascii: bool = False) -> str:
        """
        转换为JSON字符串

        Args:
            data: 转换后的数据（单条或列表）
            indent: 缩进空格数
            ensure_ascii: 是否转义非ASCII字符

        Returns:
            JSON字符串
        """
        return json.dumps(data, ensure_ascii=ensure_ascii, indent=indent, default=str)

    def to_jsonl(self, data_list: List[Dict]) -> str:
        """
        转换为JSONL格式（每行一个JSON对象）

        Args:
            data_list: 转换后的数据列表

        Returns:
            JSONL字符串
        """
        lines = []
        for item in data_list:
            lines.append(json.dumps(item, ensure_ascii=False, default=str))
        return "\n".join(lines)

    def save_json(self, data: Union[Dict, List[Dict]], file_path: str, **kwargs):
        """
        保存为JSON文件

        Args:
            data: 数据
            file_path: 输出文件路径
        """
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json(data, **kwargs))
        logger.info(f"JSON已保存: {file_path}")

    def save_jsonl(self, data_list: List[Dict], file_path: str):
        """
        保存为JSONL文件

        Args:
            data_list: 数据列表
            file_path: 输出文件路径
        """
        with open(file_path, "w", encoding="utf-8") as f:
            for item in data_list:
                f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        logger.info(f"JSONL已保存: {file_path} ({len(data_list)}行)")

    def get_stats(self) -> Dict[str, Any]:
        """获取转换统计信息"""
        return {
            "schema_name": self.schema.schema_name,
            "schema_version": self.schema.version,
            "field_count": len(self.schema.fields),
            "required_fields": self.schema.get_required_fields(),
            "conversion_count": self._conversion_count,
        }


# 全局通用转换器实例
converter = Converter()
