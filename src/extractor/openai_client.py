# -*- coding: utf-8 -*-
"""
OpenAI 兼容接口客户端
兼容 OpenAI、DeepSeek、Moonshot 等使用 OpenAI SDK 格式的模型厂商
"""
from typing import Dict, List, Optional

from .base_llm_client import BaseLLMClient, LLMClientError, LLMRateLimitError, LLMAuthError
from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class OpenAIClient(BaseLLMClient):
    """OpenAI 兼容接口客户端"""

    provider_name = "openai"

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None,
                 model: Optional[str] = None, **kwargs):
        super().__init__(
            api_key=api_key or config.OPENAI_API_KEY,
            api_base=api_base or config.OPENAI_API_BASE,
            model=model or "gpt-4o",
            **kwargs,
        )
        self._client = None

    @staticmethod
    def default_model() -> str:
        return "gpt-4o"

    def _get_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise LLMClientError(
                    "openai SDK未安装，请执行: pip install openai",
                    provider=self.provider_name,
                )
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
            )
        return self._client

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        调用 OpenAI Chat API

        Args:
            messages: 消息列表
            **kwargs: temperature, top_p, max_tokens 等

        Returns:
            模型回复文本
        """
        if not self.api_key:
            raise LLMAuthError("OpenAI API Key 未配置", provider=self.provider_name)

        client = self._get_client()

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
