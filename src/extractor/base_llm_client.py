# -*- coding: utf-8 -*-
"""
LLM客户端抽象基类
定义统一的大模型调用接口，所有厂商客户端必须继承此基类
"""
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..utils.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LLMClientError(Exception):
    """LLM调用异常"""
    def __init__(self, message: str, provider: str = "", status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class LLMRateLimitError(LLMClientError):
    """API限流异常"""
    pass


class LLMAuthError(LLMClientError):
    """API认证异常"""
    pass


class BaseLLMClient(ABC):
    """
    LLM客户端抽象基类
    所有厂商客户端必须实现 chat 方法
    """

    provider_name: str = "base"

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None,
                 model: Optional[str] = None, max_retries: Optional[int] = None,
                 retry_interval: Optional[int] = None):
        """
        Args:
            api_key: API密钥（默认从配置读取）
            api_base: API基础URL（默认从配置读取）
            model: 模型名称
            max_retries: API调用最大重试次数
            retry_interval: 重试间隔（秒）
        """
        self.api_key = api_key or ""
        self.api_base = api_base or ""
        self.model = model or self.default_model()
        self.max_retries = max_retries or config.MAX_RETRY_COUNT
        self.retry_interval = retry_interval or config.RETRY_INTERVAL

    @staticmethod
    def default_model() -> str:
        """子类可重写默认模型"""
        return "default"

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        发送对话请求

        Args:
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
            **kwargs: 温度、top_p等模型参数

        Returns:
            模型回复文本
        """
        pass

    def chat_with_retry(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        带自动重试的对话请求
        处理限流、超时等常见异常

        Args:
            messages: 消息列表
            **kwargs: 模型参数

        Returns:
            模型回复文本

        Raises:
            LLMClientError: 重试耗尽后抛出
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                return self.chat(messages, **kwargs)
            except LLMAuthError:
                raise  # 认证错误不重试
            except LLMRateLimitError as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = self.retry_interval * (2 ** attempt)  # 指数退避
                    logger.warning(
                        f"[{self.provider_name}] API限流，{wait}秒后重试 "
                        f"(第{attempt + 1}/{self.max_retries}次)"
                    )
                    time.sleep(wait)
            except LLMClientError as e:
                last_error = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"[{self.provider_name}] 调用失败: {e}，"
                        f"{self.retry_interval}秒后重试 (第{attempt + 1}/{self.max_retries}次)"
                    )
                    time.sleep(self.retry_interval)
            except Exception as e:
                last_error = LLMClientError(str(e), provider=self.provider_name)
                if attempt < self.max_retries:
                    logger.warning(
                        f"[{self.provider_name}] 未知异常: {e}，"
                        f"{self.retry_interval}秒后重试 (第{attempt + 1}/{self.max_retries}次)"
                    )
                    time.sleep(self.retry_interval)

        raise LLMClientError(
            f"[{self.provider_name}] 重试{self.max_retries}次后仍失败: {last_error}",
            provider=self.provider_name,
        )

    def extract_json_from_response(self, text: str) -> str:
        """
        从LLM回复中提取JSON部分
        处理模型返回非纯JSON的情况（如包裹在```json```中）

        Args:
            text: 模型原始回复

        Returns:
            清理后的JSON字符串
        """
        import re
        # 尝试提取 ```json ... ``` 包裹的内容
        json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if json_match:
            return json_match.group(1).strip()

        # 尝试提取 { ... } 或 [ ... ] 结构
        # 先找最外层大括号
        brace_start = text.find('{')
        bracket_start = text.find('[')

        if brace_start == -1 and bracket_start == -1:
            return text.strip()

        if brace_start != -1 and (bracket_start == -1 or brace_start < bracket_start):
            # 尝试匹配大括号
            depth = 0
            start = brace_start
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1].strip()
        else:
            # 匹配方括号
            depth = 0
            start = bracket_start
            for i in range(start, len(text)):
                if text[i] == '[':
                    depth += 1
                elif text[i] == ']':
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1].strip()

        return text.strip()

    @staticmethod
    def build_messages(
        system_prompt: str,
        user_content: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        构建标准消息列表

        Args:
            system_prompt: 系统提示词
            user_content: 用户输入内容
            history: 历史对话记录

        Returns:
            标准化的消息列表
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages
