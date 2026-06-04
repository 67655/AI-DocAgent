# -*- coding: utf-8 -*-
"""
信息抽取引擎
封装LLM调用 + Prompt管理 + 输出清洗，提供统一的信息抽取接口
"""
import json
from typing import Any, Callable, Dict, List, Optional

from .base_llm_client import BaseLLMClient
from .llm_factory import LLMFactory, llm_factory
from ..utils.logger import get_logger
from ..utils.md5_utils import deduplicator

logger = get_logger(__name__)


# ============================
# 内置通用Prompt模板
# ============================
DEFAULT_EXTRACTION_PROMPT = """
你是一个专业的信息抽取助手。请从以下文本中提取关键信息，并以JSON格式返回。

## 提取要求
1. 提取文本中的关键实体、属性、关系信息
2. 保持信息的原始语义，不要添加主观解读
3. 如果某字段在文本中未提及，请使用 null
4. 严格按JSON格式输出，不要添加任何解释文本

## 输入文本
{text}

## 输出格式
请直接输出JSON，格式如下：
```json
{{
    "entities": [
        {{"name": "实体名称", "type": "实体类型", "attributes": {{}}}}
    ],
    "summary": "文本内容简要总结"
}}
```
"""

GENERIC_KV_EXTRACTION_PROMPT = """
你是一个文档信息结构化抽取助手。请从以下文本中提取所有有价值的结构化信息。

## 文本内容
{text}

## 输出要求
1. 以JSON对象格式输出，键值对形式
2. 键名使用简洁的英文snake_case命名
3. 值保持原文表述，不要改写
4. 无法确定的信息省略该字段
5. 仅输出JSON，不添加任何额外文本
"""


class InfoExtractor:
    """
    通用信息抽取器
    组合LLM客户端和Prompt模板，提供高层抽取API
    """

    def __init__(
        self,
        client: Optional[BaseLLMClient] = None,
        provider: Optional[str] = None,
        default_prompt: Optional[str] = None,
    ):
        """
        Args:
            client: LLM客户端实例（优先使用）
            provider: LLM厂商名称（无client时自动创建）
            default_prompt: 默认Prompt模板
        """
        if client:
            self.client = client
        else:
            self.client = llm_factory.get_client(provider=provider)

        self.default_prompt = default_prompt or DEFAULT_EXTRACTION_PROMPT
        self._custom_prompts: Dict[str, str] = {}  # 自定义Prompt库

    def register_prompt(self, name: str, prompt_template: str):
        """
        注册自定义Prompt模板

        Args:
            name: Prompt名称
            prompt_template: Prompt模板（可用 {text} 占位符）
        """
        self._custom_prompts[name] = prompt_template
        logger.debug(f"注册Prompt模板: {name}")

    def get_prompt(self, name: Optional[str] = None) -> str:
        """
        获取Prompt模板

        Args:
            name: Prompt名称，None则使用默认

        Returns:
            Prompt模板字符串
        """
        if name and name in self._custom_prompts:
            return self._custom_prompts[name]
        return self.default_prompt

    def extract(
        self,
        text: str,
        prompt_name: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        **llm_kwargs,
    ) -> Dict[str, Any]:
        """
        从文本中抽取信息

        Args:
            text: 待抽取的文本内容
            prompt_name: 使用的Prompt模板名称
            custom_prompt: 自定义Prompt（覆盖prompt_name和默认Prompt）
            **llm_kwargs: 传递给LLM的其他参数

        Returns:
            抽取结果的字典，包含：
            - success: 是否成功
            - data: 解析后的JSON数据
            - raw_response: LLM原始返回
            - error: 错误信息
        """
        # 选择Prompt模板
        if custom_prompt:
            prompt_template = custom_prompt
        else:
            prompt_template = self.get_prompt(prompt_name)

        # 构建用户消息
        user_content = prompt_template.replace("{text}", text)

        # 构建消息列表
        messages = BaseLLMClient.build_messages(
            system_prompt="你是一个精准的信息抽取助手。严格按JSON格式返回结果。",
            user_content=user_content,
        )

        try:
            raw_response = self.client.chat_with_retry(messages, **llm_kwargs)

            # 清理并解析JSON
            json_str = self.client.extract_json_from_response(raw_response)

            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试用json5或返回原始文本
                try:
                    import json5
                    data = json5.loads(json_str)
                except ImportError:
                    data = {"raw_text": raw_response}
                    logger.warning(f"JSON解析失败，返回原始文本")

            return {
                "success": True,
                "data": data,
                "raw_response": raw_response,
                "error": None,
                "content_md5": deduplicator.compute_md5(text),
            }

        except Exception as e:
            logger.error(f"信息抽取失败: {e}")
            return {
                "success": False,
                "data": None,
                "raw_response": None,
                "error": str(e),
                "content_md5": deduplicator.compute_md5(text),
            }

    def batch_extract(
        self,
        texts: List[str],
        prompt_name: Optional[str] = None,
        dedup: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **llm_kwargs,
    ) -> List[Dict[str, Any]]:
        """
        批量抽取

        Args:
            texts: 待抽取的文本列表
            prompt_name: Prompt模板名称
            dedup: 是否对输入文本去重（基于MD5）
            progress_callback: 进度回调 callback(completed, total)
            **llm_kwargs: LLM参数

        Returns:
            抽取结果列表
        """
        results = []
        total = len(texts)

        for i, text in enumerate(texts):
            # MD5去重：跳过已处理的完全相同文本
            if dedup and deduplicator.is_duplicate(text):
                logger.info(f"跳过重复文本 ({i + 1}/{total})")
                results.append({
                    "success": True,
                    "data": None,
                    "raw_response": None,
                    "error": None,
                    "content_md5": deduplicator.compute_md5(text),
                    "skipped": True,
                    "skip_reason": "duplicate_content",
                })
                if progress_callback:
                    progress_callback(i + 1, total)
                continue

            result = self.extract(text, prompt_name=prompt_name, **llm_kwargs)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total)

            logger.info(f"抽取进度: {i + 1}/{total}")

        return results
