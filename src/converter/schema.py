# -*- coding: utf-8 -*-
"""
输出模式定义模块
定义目标JSON Schema、字段映射规则、字段校验规则
"""
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Union


class FieldRule:
    """单字段转换规则"""

    def __init__(
        self,
        target_key: str,
        source_keys: Optional[List[str]] = None,
        required: bool = False,
        default: Any = None,
        field_type: Optional[Union[type, str]] = None,
        validators: Optional[List[Callable[[Any], bool]]] = None,
        normalizers: Optional[List[Callable[[Any], Any]]] = None,
        description: str = "",
    ):
        """
        Args:
            target_key: 目标字段名
            source_keys: 可选来源字段名列表（按优先级匹配），None则按target_key匹配
            required: 是否必填
            default: 默认值
            field_type: 期望类型（str/int/float/bool/list/dict）
            validators: 自定义校验函数列表
            normalizers: 自定义规范化函数列表
            description: 字段描述
        """
        self.target_key = target_key
        self.source_keys = source_keys or [target_key]
        self.required = required
        self.default = default
        self.field_type = field_type
        self.validators = validators or []
        self.normalizers = normalizers or []
        self.description = description


class OutputSchema:
    """
    输出模式定义
    定义目标JSON结构、字段映射和转换规则
    """

    def __init__(self, schema_name: str = "default", version: str = "1.0"):
        """
        Args:
            schema_name: Schema名称
            version: 版本号
        """
        self.schema_name = schema_name
        self.version = version
        self.fields: Dict[str, FieldRule] = {}
        self._output_template: Dict[str, Any] = {}
        self._description: str = ""

    def add_field(self, rule: FieldRule):
        """添加字段规则"""
        self.fields[rule.target_key] = rule
        # 构建输出模板
        self._output_template[rule.target_key] = rule.default

    def add_fields_batch(self, field_defs: List[Dict]):
        """
        批量添加字段规则

        Args:
            field_defs: 字段定义列表，每项为FieldRule构造参数字典
        """
        for fd in field_defs:
            self.add_field(FieldRule(**fd))

    def set_description(self, desc: str):
        """设置Schema描述"""
        self._description = desc

    def get_field_names(self) -> List[str]:
        """获取所有字段名"""
        return list(self.fields.keys())

    def get_required_fields(self) -> List[str]:
        """获取所有必填字段名"""
        return [k for k, v in self.fields.items() if v.required]

    def get_output_template(self) -> Dict[str, Any]:
        """获取输出模板（所有字段默认值）"""
        return deepcopy(self._output_template)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于JSON持久化）"""
        fields_info = {}
        for key, rule in self.fields.items():
            fields_info[key] = {
                "source_keys": rule.source_keys,
                "required": rule.required,
                "default": rule.default,
                "field_type": str(rule.field_type) if rule.field_type else None,
                "description": rule.description,
            }
        return {
            "schema_name": self.schema_name,
            "version": self.version,
            "description": self._description,
            "fields": fields_info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputSchema":
        """从字典反序列化"""
        schema = cls(
            schema_name=data.get("schema_name", "imported"),
            version=data.get("version", "1.0"),
        )
        schema.set_description(data.get("description", ""))
        for key, fd in data.get("fields", {}).items():
            rule = FieldRule(
                target_key=key,
                source_keys=fd.get("source_keys", [key]),
                required=fd.get("required", False),
                default=fd.get("default"),
                field_type=fd.get("field_type"),
                description=fd.get("description", ""),
            )
            schema.add_field(rule)
        return schema

    @classmethod
    def create_generic_schema(cls) -> "OutputSchema":
        """创建通用抽取结果Schema"""
        schema = cls(schema_name="generic_extraction", version="1.0")
        schema.set_description("通用文档信息抽取输出Schema")
        schema.add_fields_batch([
            {"target_key": "doc_id", "source_keys": ["doc_id", "document_id", "id"], "required": True, "default": "", "field_type": "str", "description": "文档唯一标识"},
            {"target_key": "source_file", "source_keys": ["source_file", "file_path", "source"], "required": False, "default": "", "field_type": "str", "description": "来源文件路径"},
            {"target_key": "title", "source_keys": ["title", "name", "标题"], "required": False, "default": "", "field_type": "str", "description": "文档标题"},
            {"target_key": "content_type", "source_keys": ["content_type", "type", "category"], "required": False, "default": "document", "field_type": "str", "description": "内容类型"},
            {"target_key": "entities", "source_keys": ["entities", "items", "data"], "required": False, "default": [], "field_type": "list", "description": "抽取的实体列表"},
            {"target_key": "summary", "source_keys": ["summary", "abstract", "description"], "required": False, "default": "", "field_type": "str", "description": "内容摘要"},
            {"target_key": "keywords", "source_keys": ["keywords", "tags", "key_words"], "required": False, "default": [], "field_type": "list", "description": "关键词列表"},
            {"target_key": "extraction_time", "source_keys": ["extraction_time", "timestamp", "created_at"], "required": False, "default": "", "field_type": "str", "description": "抽取时间"},
            {"target_key": "confidence", "source_keys": ["confidence", "score", "置信度"], "required": False, "default": None, "field_type": "float", "description": "置信度"},
            {"target_key": "raw_text", "source_keys": ["raw_text", "text", "content", "原文"], "required": False, "default": "", "field_type": "str", "description": "原始文本"},
        ])
        return schema
