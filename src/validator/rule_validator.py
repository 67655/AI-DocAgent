# -*- coding: utf-8 -*-
"""
规则校验器
实现字段完整性、格式、内容准确性等规则级校验
"""
import re
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class ValidationLevel(str, Enum):
    """校验级别"""
    ERROR = "error"       # 严重问题，数据不可用
    WARNING = "warning"   # 警告，数据可能有问题
    INFO = "info"         # 提示信息


class ValidationResult:
    """单条校验结果"""

    def __init__(self, field: str = "", level: ValidationLevel = ValidationLevel.INFO,
                 message: str = "", rule_name: str = ""):
        self.field = field
        self.level = level
        self.message = message
        self.rule_name = rule_name

    def is_valid(self) -> bool:
        """是否通过校验（WARNING和INFO视为通过，只有ERROR不通过）"""
        return self.level != ValidationLevel.ERROR

    def to_dict(self) -> Dict:
        return {
            "field": self.field,
            "level": self.level.value,
            "pass": self.is_valid(),
            "message": self.message,
            "rule": self.rule_name,
        }


class RuleValidator:
    """
    规则校验器
    对数据字段进行规则级校验：必填、类型、格式、长度、自定义规则等
    """

    def __init__(self):
        self._rules: Dict[str, List[Tuple[str, Callable[[Any], bool], str]]] = {}

    def add_required_rule(self, field: str):
        """添加必填校验"""
        self._add_rule(field, "required", lambda v: v is not None and v != "" and v != [],
                       f"字段 '{field}' 不能为空")

    def add_type_rule(self, field: str, expected_type: type):
        """添加类型校验"""
        self._add_rule(field, "type_check",
                       lambda v: v is None or isinstance(v, expected_type),
                       f"字段 '{field}' 类型应为 {expected_type.__name__}")

    def add_regex_rule(self, field: str, pattern: str, message: str = ""):
        """添加正则格式校验"""
        self._add_rule(field, "regex",
                       lambda v: v is None or bool(re.match(pattern, str(v))),
                       message or f"字段 '{field}' 不匹配格式: {pattern}")

    def add_length_rule(self, field: str, min_len: int = 0, max_len: int = None):
        """添加长度校验"""
        desc = f"长度应在 {min_len}"
        if max_len is not None:
            desc += f"-{max_len}"
            self._add_rule(field, "length",
                           lambda v: v is None or min_len <= len(str(v)) <= max_len,
                           f"字段 '{field}' {desc}")
        else:
            self._add_rule(field, "length",
                           lambda v: v is None or len(str(v)) >= min_len,
                           f"字段 '{field}' {desc}")

    def add_range_rule(self, field: str, min_val: float = None, max_val: float = None):
        """添加数值范围校验"""
        desc_parts = []
        if min_val is not None:
            desc_parts.append(f">= {min_val}")
        if max_val is not None:
            desc_parts.append(f"<= {max_val}")
        desc = "，".join(desc_parts)

        def check(v):
            if v is None:
                return True
            try:
                num = float(v)
                if min_val is not None and num < min_val:
                    return False
                if max_val is not None and num > max_val:
                    return False
                return True
            except (ValueError, TypeError):
                return False

        self._add_rule(field, "range", check, f"字段 '{field}' {desc}")

    def add_custom_rule(self, field: str, rule_name: str, check_func: Callable[[Any], bool],
                        message: str = ""):
        """添加自定义校验规则"""
        self._add_rule(field, rule_name, check_func, message or f"自定义规则 '{rule_name}' 未通过")

    def _add_rule(self, field: str, rule_name: str, check_func: Callable[[Any], bool], message: str):
        """内部：注册规则"""
        if field not in self._rules:
            self._rules[field] = []
        self._rules[field].append((rule_name, check_func, message))

    def validate_one(self, data: Dict[str, Any], strict: bool = False) -> List[ValidationResult]:
        """
        校验单条数据

        Args:
            data: 待校验数据字典
            strict: 是否严格模式（首个ERROR即停止）

        Returns:
            校验结果列表
        """
        results = []

        for field, rules in self._rules.items():
            value = data.get(field)
            for rule_name, check_func, message in rules:
                try:
                    passed = check_func(value)
                except Exception:
                    passed = False

                if not passed:
                    result = ValidationResult(
                        field=field,
                        level=ValidationLevel.ERROR,
                        message=message,
                        rule_name=rule_name,
                    )
                    results.append(result)
                    if strict:
                        return results

        if not results:
            results.append(ValidationResult(
                level=ValidationLevel.INFO,
                message="所有字段校验通过",
                rule_name="all_pass",
            ))

        return results

    def validate_batch(self, data_list: List[Dict[str, Any]]) -> List[List[ValidationResult]]:
        """
        批量校验

        Args:
            data_list: 数据字典列表

        Returns:
            每条数据的校验结果列表
        """
        return [self.validate_one(data) for data in data_list]

    def is_all_valid(self, validation_results: List[ValidationResult]) -> bool:
        """判断是否全部通过（无ERROR）"""
        return all(r.is_valid() for r in validation_results)

    def filter_valid(self, data_list: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """
        将数据分为合格与不合格两组

        Args:
            data_list: 数据列表

        Returns:
            (valid_data, invalid_data) 两个列表
        """
        valid = []
        invalid = []
        for data in data_list:
            results = self.validate_one(data)
            if self.is_all_valid(results):
                valid.append(data)
            else:
                invalid.append({
                    "data": data,
                    "errors": [r.to_dict() for r in results if not r.is_valid()],
                })
        return valid, invalid

    def get_rules_summary(self) -> Dict[str, List[str]]:
        """获取已注册规则的摘要"""
        summary = {}
        for field, rules in self._rules.items():
            summary[field] = [r[0] for r in rules]
        return summary
