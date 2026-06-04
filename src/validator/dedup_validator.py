# -*- coding: utf-8 -*-
"""
去重校验器
基于MD5指纹进行数据重复检测
"""
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.md5_utils import MD5Deduplicator
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DedupValidator:
    """
    去重校验器
    对数据内容进行MD5去重检测，区分全局去重和字段级去重
    """

    def __init__(self, deduplicator: Optional[MD5Deduplicator] = None):
        """
        Args:
            deduplicator: MD5去重器实例（None则使用全局单例）
        """
        from ..utils.md5_utils import deduplicator as global_dedup
        self.deduplicator = deduplicator or global_dedup

    def check_content_duplicate(self, content: Any, doc_id: str = "") -> Dict[str, Any]:
        """
        检查内容是否重复

        Args:
            content: 待检测的内容
            doc_id: 文档ID

        Returns:
            {"is_duplicate": bool, "fingerprint": str, "existing_doc_id": str}
        """
        fingerprint = self.deduplicator.compute_md5(content)
        existing_doc = self.deduplicator.get_doc_id(fingerprint)

        is_dup = fingerprint in set(self.deduplicator._global_fingerprints)

        result = {
            "is_duplicate": is_dup,
            "fingerprint": fingerprint,
            "existing_doc_id": existing_doc or "",
        }

        if is_dup:
            logger.debug(f"检测到重复内容: {doc_id}, 指纹: {fingerprint[:12]}...")
        else:
            # 注册为新内容
            self.deduplicator.register_fingerprint(fingerprint, doc_id=doc_id)

        return result

    def check_field_duplicate(self, data: Dict[str, Any], field: str, doc_id: str = "") -> Dict[str, Any]:
        """
        检查指定字段值是否重复

        Args:
            data: 数据字典
            field: 要检测的字段名
            doc_id: 文档ID

        Returns:
            同 check_content_duplicate
        """
        value = data.get(field, "")
        return self.check_content_duplicate(value, doc_id=doc_id)

    def dedup_batch(
        self,
        data_list: List[Dict[str, Any]],
        dedup_field: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        批量去重，将数据分为去重后数据和重复数据

        Args:
            data_list: 数据列表
            dedup_field: 去重依据字段（None则全内容比对）

        Returns:
            (unique_data, duplicate_data) 两个列表
        """
        unique = []
        duplicates = []

        for i, data in enumerate(data_list):
            if dedup_field:
                content = data.get(dedup_field, f"__empty__{i}")
            else:
                content = str(data)

            result = self.check_content_duplicate(content, doc_id=str(i))
            if result["is_duplicate"]:
                duplicates.append({
                    "data": data,
                    "fingerprint": result["fingerprint"],
                    "duplicate_of_doc_id": result["existing_doc_id"],
                })
            else:
                unique.append(data)

        logger.info(f"批量去重完成: {len(unique)}条唯一, {len(duplicates)}条重复")
        return unique, duplicates

    def get_fingerprint(self, data: Any) -> str:
        """获取数据的MD5指纹"""
        return self.deduplicator.compute_md5(data)

    def clear_cache(self):
        """清空去重缓存"""
        self.deduplicator.clear()
