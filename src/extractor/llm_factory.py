# -*- coding: utf-8 -*-
"""
LLM客户端工厂
根据provider名称自动创建对应的客户端实例
"""
from typing import Dict, Optional, Type

from .base_llm_client import BaseLLMClient
from .qwen_client import QwenClient
from .zhipu_client import ZhipuClient
from .openai_client import OpenAIClient
from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LLMFactory:
    """
    LLM客户端工厂
    支持内置厂商 + 自定义注册
    """

    def __init__(self):
        self._clients: Dict[str, Type[BaseLLMClient]] = {}
        self._register_builtin()

    def _register_builtin(self):
        """注册内置客户端"""
        self.register("qwen", QwenClient)
        self.register("zhipu", ZhipuClient)
        self.register("openai", OpenAIClient)

    def register(self, provider: str, client_class: Type[BaseLLMClient]):
        """
        注册自定义LLM客户端

        Args:
            provider: 厂商名称标识
            client_class: 客户端类（需继承BaseLLMClient）
        """
        self._clients[provider.lower()] = client_class
        logger.debug(f"注册LLM客户端: {provider} -> {client_class.__name__}")

    def get_client(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> BaseLLMClient:
        """
        获取LLM客户端实例

        Args:
            provider: 厂商名称 (qwen/zhipu/openai)，默认使用配置值
            api_key: API密钥（可选，默认从配置读取）
            api_base: API基础URL（可选，默认从配置读取）
            model: 模型名称（可选，默认使用厂商默认模型）
            **kwargs: 传递给客户端构造函数的其他参数

        Returns:
            BaseLLMClient 实例

        Raises:
            ValueError: 不支持的厂商名称
        """
        provider = (provider or config.DEFAULT_LLM_PROVIDER).lower()

        if provider not in self._clients:
            available = ", ".join(self._clients.keys())
            raise ValueError(f"不支持的LLM厂商: {provider}，可用: {available}")

        client_class = self._clients[provider]
        client = client_class(
            api_key=api_key,
            api_base=api_base,
            model=model,
            **kwargs,
        )
        logger.info(f"创建LLM客户端: {provider} (模型: {client.model})")
        return client

    def list_providers(self) -> list:
        """列出所有已注册的厂商"""
        return list(self._clients.keys())

    def create_with_env(self, provider: str) -> BaseLLMClient:
        """
        通过环境变量自动创建客户端
        根据provider自动读取对应的 API_KEY 和 API_BASE

        Args:
            provider: 厂商名称

        Returns:
            BaseLLMClient 实例
        """
        provider = provider.lower()
        return self.get_client(provider=provider)


# 全局LLM工厂实例
llm_factory = LLMFactory()
