# -*- coding: utf-8 -*-
"""
通义千问 (DashScope) 客户端
"""
from typing import Dict, List, Optional

from .base_llm_client import BaseLLMClient, LLMClientError, LLMRateLimitError, LLMAuthError
from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class QwenClient(BaseLLMClient):
    """通义千问 DashScope 客户端"""

    provider_name = "qwen"

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None,
                 model: Optional[str] = None, **kwargs):
        super().__init__(
            api_key=api_key or config.DASHSCOPE_API_KEY,
            api_base=api_base or config.DASHSCOPE_API_BASE,
            model=model or "qwen-plus",
            **kwargs,
        )

    @staticmethod
    def default_model() -> str:
        return "qwen-plus"

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        调用通义千问 API

        支持两种调用方式：
        1. DashScope SDK（优先）
        2. OpenAI 兼容接口（回退）

        Args:
            messages: 消息列表
            **kwargs: temperature, top_p 等

        Returns:
            模型回复文本
        """
        if not self.api_key:
            raise LLMAuthError("DashScope API Key 未配置", provider=self.provider_name)

        # 优先使用 OpenAI 兼容模式（DashScope 支持）
        try:
            from openai import OpenAI
        except ImportError:
            return self._call_via_dashscope_sdk(messages, **kwargs)

        return self._call_via_openai_compat(messages, **kwargs)

    def _call_via_openai_compat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """通过 OpenAI 兼容接口调用"""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
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

    def _call_via_dashscope_sdk(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """通过 DashScope 原生 SDK 调用"""
        try:
            import dashscope
        except ImportError:
            raise LLMClientError(
                "dashscope SDK未安装，请执行: pip install dashscope",
                provider=self.provider_name,
            )

        from dashscope import Generation

        try:
            response = Generation.call(
                model=self.model,
                messages=messages,
                api_key=self.api_key,
                temperature=kwargs.get("temperature", 0.1),
                top_p=kwargs.get("top_p", 0.9),
                max_tokens=kwargs.get("max_tokens", 4096),
                result_format="message",
            )

            if response.status_code == 200:
                return response.output.choices[0].message.content
            else:
                code = response.status_code
                msg = response.message or "未知错误"
                if code == 429:
                    raise LLMRateLimitError(msg, provider=self.provider_name)
                if code in (401, 403):
                    raise LLMAuthError(msg, provider=self.provider_name)
                raise LLMClientError(
                    f"DashScope错误 [code={code}]: {msg}",
                    provider=self.provider_name,
                    status_code=code,
                )

        except (LLMRateLimitError, LLMAuthError, LLMClientError):
            raise
        except Exception as e:
            raise LLMClientError(str(e), provider=self.provider_name)
