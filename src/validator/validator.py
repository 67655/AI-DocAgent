# -*- coding: utf-8 -*-
"""
数据质量校验器
整合规则校验、去重校验、模型复检判定，提供统一质量检查接口
"""
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .rule_validator import RuleValidator, ValidationResult, ValidationLevel
from .dedup_validator import DedupValidator
from ..utils.logger import get_logger

logger = get_logger(__name__)


class QualityValidator:
    """
    数据质量综合校验器
    按校验流水线依次执行：规则校验 → 去重检测 → (可选)模型复检判定
    """

    def __init__(
        self,
        rule_validator: Optional[RuleValidator] = None,
        dedup_validator: Optional[DedupValidator] = None,
        recheck_threshold: float = 0.6,
    ):
        """
        Args:
            rule_validator: 规则校验器实例
            dedup_validator: 去重校验器实例
            recheck_threshold: 低置信度阈值，低于此值的数据将被标记为需要模型复检
        """
        self.rule_validator = rule_validator or RuleValidator()
        self.dedup_validator = dedup_validator or DedupValidator()
        self.recheck_threshold = recheck_threshold

        # 异常数据归档
        self._error_archive: List[Dict] = []
        self._recheck_queue: List[Dict] = []

    def validate(
        self,
        data: Dict[str, Any],
        check_dedup: bool = True,
        dedup_field: Optional[str] = None,
        doc_id: str = "",
    ) -> Dict[str, Any]:
        """
        对单条数据进行完整质量检查

        Args:
            data: 待校验的数据字典
            check_dedup: 是否进行去重检测
            dedup_field: 去重字段
            doc_id: 文档ID

        Returns:
            校验报告字典：
            {
                "pass": bool,
                "rule_results": [...],
                "dedup_result": {...},
                "needs_recheck": bool,
                "recheck_reason": str,
                "timestamp": str,
            }
        """
        report = {
            "pass": True,
            "doc_id": doc_id,
            "rule_results": [],
            "dedup_result": None,
            "needs_recheck": False,
            "recheck_reason": "",
            "timestamp": datetime.now().isoformat(),
        }

        # 1. 规则校验
        rule_results = self.rule_validator.validate_one(data)
        report["rule_results"] = [r.to_dict() for r in rule_results]

        rule_pass = all(r.is_valid() for r in rule_results)
        if not rule_pass:
            report["pass"] = False
            errors = [r.message for r in rule_results if not r.is_valid()]
            report["recheck_reason"] = f"规则校验失败: {'; '.join(errors)}"

        # 2. 去重检测
        if check_dedup:
            if dedup_field:
                dedup_result = self.dedup_validator.check_field_duplicate(
                    data, dedup_field, doc_id=doc_id
                )
            else:
                dedup_result = self.dedup_validator.check_content_duplicate(
                    str(data), doc_id=doc_id
                )
            report["dedup_result"] = dedup_result

            if dedup_result["is_duplicate"]:
                report["pass"] = False
                report["recheck_reason"] = (
                    f"内容重复 (指纹: {dedup_result['fingerprint'][:12]}...)"
                )

        # 3. 低置信度模型复检判定
        confidence = data.get("confidence", data.get("score", 1.0))
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 1.0

        if confidence < self.recheck_threshold:
            report["needs_recheck"] = True
            if not report["recheck_reason"]:
                report["recheck_reason"] = f"置信度过低 ({confidence:.2f} < {self.recheck_threshold})"

        # 4. 异常数据归档
        if not report["pass"] or report["needs_recheck"]:
            self._error_archive.append({
                "data": data,
                "report": report,
            })

        if report["needs_recheck"]:
            self._recheck_queue.append({
                "data": data,
                "confidence": confidence,
                "reason": report["recheck_reason"],
            })

        return report

    def validate_batch(
        self,
        data_list: List[Dict[str, Any]],
        check_dedup: bool = True,
        dedup_field: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        批量质量检查

        Args:
            data_list: 数据列表
            check_dedup: 是否去重
            dedup_field: 去重字段
            progress_callback: 进度回调

        Returns:
            批量校验汇总报告
        """
        results = []
        passed = []
        failed = []

        total = len(data_list)
        for i, data in enumerate(data_list):
            report = self.validate(
                data,
                check_dedup=check_dedup,
                dedup_field=dedup_field,
                doc_id=str(i),
            )
            results.append(report)
            if report["pass"]:
                passed.append(data)
            else:
                failed.append({
                    "data": data,
                    "report": report,
                })

            if progress_callback:
                progress_callback(i + 1, total)

        summary = {
            "total": total,
            "passed": len(passed),
            "failed": len(failed),
            "needs_recheck": len(self._recheck_queue),
            "pass_rate": round(len(passed) / total * 100, 2) if total > 0 else 0,
            "timestamp": datetime.now().isoformat(),
            "detailed_results": results,
        }

        logger.info(
            f"批量校验完成: {summary['passed']}/{total}通过, "
            f"{summary['failed']}失败, {summary['needs_recheck']}需复检"
        )
        return summary

    def get_error_archive(self) -> List[Dict]:
        """获取异常数据归档"""
        return self._error_archive

    def get_recheck_queue(self) -> List[Dict]:
        """获取待模型复检的数据"""
        return self._recheck_queue

    def export_error_archive(self, file_path: str):
        """导出异常数据归档为JSON文件"""
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "count": len(self._error_archive),
            "records": self._error_archive,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"异常数据已归档: {file_path} ({len(self._error_archive)}条)")

    def clear(self):
        """清空所有归档和队列"""
        self._error_archive.clear()
        self._recheck_queue.clear()
        self.dedup_validator.clear_cache()


# 全局质量校验器实例
quality_validator = QualityValidator()
