# -*- coding: utf-8 -*-
"""
MD5去重工具模块
提供内容指纹生成、全局去重比对、本地去重缓存功能
"""
import hashlib
from typing import Any, Dict, Optional, Set


class MD5Deduplicator:
    """
    MD5全局去重器
    用于对文档内容生成MD5指纹，并与历史指纹库比对去重
    """

    def __init__(self):
        """初始化去重器"""
        self._global_fingerprints: Set[str] = set()  # 内存指纹缓存
        self._fingerprint_records: Dict[str, str] = {}  # fingerprint -> doc_id 映射

    @staticmethod
    def compute_md5(content: Any) -> str:
        """
        计算内容的MD5摘要

        Args:
            content: 待计算的内容（字符串、字节、或可转为字符串的对象）

        Returns:
            32位小写MD5十六进制字符串
        """
        if isinstance(content, bytes):
            data = content
        elif isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = str(content).encode("utf-8")
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def compute_md5_file(file_path: str, chunk_size: int = 8192) -> str:
        """
        计算文件的MD5摘要（分块读取，适合大文件）

        Args:
            file_path: 文件路径
            chunk_size: 每次读取的块大小（字节）

        Returns:
            32位小写MD5十六进制字符串
        """
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    @staticmethod
    def compute_batch_md5(contents: list) -> list:
        """
        批量计算MD5摘要

        Args:
            contents: 内容列表

        Returns:
            MD5摘要列表（与输入顺序一致）
        """
        return [MD5Deduplicator.compute_md5(c) for c in contents]

    def is_duplicate(self, content: Any, doc_id: Optional[str] = None) -> bool:
        """
        检查内容是否为重复数据

        Args:
            content: 待检查的内容
            doc_id: 文档ID（可选，用于记录映射）

        Returns:
            是否重复
        """
        fingerprint = self.compute_md5(content)
        if fingerprint in self._global_fingerprints:
            return True
        self._global_fingerprints.add(fingerprint)
        if doc_id:
            self._fingerprint_records[fingerprint] = doc_id
        return False

    def register_fingerprint(self, fingerprint: str, doc_id: Optional[str] = None):
        """
        手动注册一个已知指纹到去重库

        Args:
            fingerprint: MD5指纹
            doc_id: 关联的文档ID
        """
        self._global_fingerprints.add(fingerprint)
        if doc_id:
            self._fingerprint_records[fingerprint] = doc_id

    def load_fingerprints(self, fingerprints: list):
        """
        批量加载已有指纹到缓存（用于从数据库恢复去重状态）

        Args:
            fingerprints: 指纹列表，每个元素可以是 str 或 (fingerprint, doc_id) 元组
        """
        for item in fingerprints:
            if isinstance(item, tuple):
                fp, doc_id = item
                self._global_fingerprints.add(fp)
                if doc_id:
                    self._fingerprint_records[fp] = doc_id
            else:
                self._global_fingerprints.add(item)

    def get_doc_id(self, fingerprint: str) -> Optional[str]:
        """根据指纹获取文档ID"""
        return self._fingerprint_records.get(fingerprint)

    def get_fingerprint_count(self) -> int:
        """获取当前去重库中的指纹总数"""
        return len(self._global_fingerprints)

    def clear(self):
        """清空去重缓存"""
        self._global_fingerprints.clear()
        self._fingerprint_records.clear()

    def remove_fingerprint(self, fingerprint: str):
        """移除指定指纹"""
        self._global_fingerprints.discard(fingerprint)
        self._fingerprint_records.pop(fingerprint, None)


# 全局去重器实例
deduplicator = MD5Deduplicator()
