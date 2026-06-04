# -*- coding: utf-8 -*-
"""
智谱AI (ChatGLM) 客户端
"""
from typing import Dict, List, Optional

from .base_llm_client import BaseLLMClient, LLMClientError, LLMRateLimitError, LLMAuthError
from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ZhipuClient(BaseLLMClient):
    """智谱AI 客户端"""

    provider_name = "zhipu"

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None,
                 model: Optional[str] = None, **kwargs):
        super().__init__(
            api_key=api_key or config.ZHIPU_API_KEY,
            api_base=api_base or config.ZHIPU_API_BASE,
            model=model or "glm-4-flash",
            **kwargs,
        )

    @staticmethod
    def default_model() -> str:
        return "glm-4-flash"

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        调用智谱AI API

        支持两种调用方式：
        1. 智谱AI官方SDK（优先）
        2. OpenAI兼容接口（回退）

        Args:
            messages: 消息列表
            **kwargs: temperature, top_p 等

        Returns:
            模型回复文本
        """
        if not self.api_key:
            raise LLMAuthError("智谱AI API Key 未配置", provider=self.provider_name)

        # 优先使用智谱AI SDK
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            return self._call_via_openai_compat(messages, **kwargs)

        return self._call_via_sdk(messages, **kwargs)

    def _call_via_sdk(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """通过智谱AI官方SDK调用"""
        from zhipuai import ZhipuAI

        client = ZhipuAI(api_key=self.api_key)

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.1),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            content = response.choices[0].message.content
            return content or ""

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in str(e):
                raise LLMRateLimitError(str(e), provider=self.provider_name)
            if "auth" in error_str or "key" in error_str or "401" in str(e) or "403" in str(e):
                raise LLMAuthError(str(e), provider=self.provider_name)
            raise LLMClientError(str(e), provider=self.provider_name)

    def _call_via_openai_compat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """通过OpenAI兼容接口调用智谱AI"""
        try:
            from openai import OpenAI
        except ImportError:
            raise LLMClientError(
                "请安装 openai 或 zhipuai SDK: pip install openai zhipuai",
                provider=self.provider_name,
            )

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base or "https://open.bigmodel.cn/api/paas/v4",
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.1),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            content = response.choices[0].message.content
            return content or ""

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in str(e):
                raise LLMRateLimitError(str(e), provider=self.provider_name)
            if "auth" in error_str or "key" in error_str or "401" in str(e) or "403" in str(e):
                raise LLMAuthError(str(e), provider=self.provider_name)
            raise LLMClientError(str(e), provider=self.provider_name)
