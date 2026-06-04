# -*- coding: utf-8 -*-
"""extractor 模块单元测试（不依赖真实API调用）"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from extractor.base_llm_client import (
    BaseLLMClient,
    LLMClientError,
    LLMRateLimitError,
    LLMAuthError,
)
from extractor.llm_factory import LLMFactory, llm_factory
from extractor.extractor import (
    InfoExtractor,
    DEFAULT_EXTRACTION_PROMPT,
    GENERIC_KV_EXTRACTION_PROMPT,
)
from extractor.qwen_client import QwenClient
from extractor.zhipu_client import ZhipuClient
from extractor.openai_client import OpenAIClient


# ============================
# 自定义异常测试
# ============================
class TestLLMExceptions:
    """LLM异常类测试"""

    def test_llm_client_error(self):
        e = LLMClientError("测试错误", provider="test", status_code=500)
        assert "测试错误" in str(e)
        assert e.provider == "test"
        assert e.status_code == 500

    def test_llm_rate_limit_error(self):
        e = LLMRateLimitError("API限流")
        assert isinstance(e, LLMClientError)

    def test_llm_auth_error(self):
        e = LLMAuthError("认证失败")
        assert isinstance(e, LLMClientError)


# ============================
# BaseLLMClient 测试
# ============================
class TestBaseLLMClient:
    """基类功能测试"""

    def test_build_messages_with_system(self):
        """测试构建消息列表 - 含system prompt"""
        msgs = BaseLLMClient.build_messages(
            system_prompt="你是一个助手",
            user_content="帮我写代码",
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "你是一个助手"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "帮我写代码"

    def test_build_messages_with_history(self):
        """测试构建消息列表 - 含历史对话"""
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好，有什么可以帮你的？"},
        ]
        msgs = BaseLLMClient.build_messages(
            system_prompt="助手",
            user_content="今天天气如何",
            history=history,
        )
        assert len(msgs) == 4
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"
        assert msgs[3]["role"] == "user"

    def test_build_messages_no_system(self):
        """测试无system prompt时"""
        msgs = BaseLLMClient.build_messages(
            system_prompt="",
            user_content="直接提问",
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_extract_json_from_code_block(self):
        """测试从```json```块中提取JSON"""
        client = BaseLLMClient.__new__(BaseLLMClient)
        text = '这是回复\n```json\n{"name": "test", "value": 123}\n```\n以上是结果'
        result = client.extract_json_from_response(text)
        assert result == '{"name": "test", "value": 123}'

    def test_extract_json_plain(self):
        """测试纯JSON文本"""
        client = BaseLLMClient.__new__(BaseLLMClient)
        text = '{"entities": [{"name": "AI-DocAgent"}]}'
        result = client.extract_json_from_response(text)
        assert "AI-DocAgent" in result

    def test_extract_json_brace_matching(self):
        """测试大括号嵌套匹配"""
        client = BaseLLMClient.__new__(BaseLLMClient)
        text = '前缀文本 {"outer": {"inner": "value"}, "list": [1,2,3]} 后缀文本'
        result = client.extract_json_from_response(text)
        data = json.loads(result)
        assert data["outer"]["inner"] == "value"

    def test_extract_json_array(self):
        """测试数组格式"""
        client = BaseLLMClient.__new__(BaseLLMClient)
        text = '结果: [{"id": 1}, {"id": 2}, {"id": 3}]'
        result = client.extract_json_from_response(text)
        data = json.loads(result)
        assert len(data) == 3


# ============================
# LLMFactory 测试
# ============================
class TestLLMFactory:
    """LLM工厂测试"""

    def test_get_qwen_client(self):
        client = llm_factory.get_client("qwen", api_key="test_key")
        assert isinstance(client, QwenClient)
        assert client.provider_name == "qwen"

    def test_get_zhipu_client(self):
        client = llm_factory.get_client("zhipu", api_key="test_key")
        assert isinstance(client, ZhipuClient)
        assert client.provider_name == "zhipu"

    def test_get_openai_client(self):
        client = llm_factory.get_client("openai", api_key="test_key")
        assert isinstance(client, OpenAIClient)
        assert client.provider_name == "openai"

    def test_get_client_case_insensitive(self):
        client = llm_factory.get_client("QWEN", api_key="test_key")
        assert isinstance(client, QwenClient)

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="不支持的LLM厂商"):
            llm_factory.get_client("unknown_provider")

    def test_list_providers(self):
        providers = llm_factory.list_providers()
        assert "qwen" in providers
        assert "zhipu" in providers
        assert "openai" in providers

    def test_register_custom_client(self):
        """测试注册自定义客户端"""

        class CustomClient(BaseLLMClient):
            provider_name = "custom"

            @staticmethod
            def default_model():
                return "custom-v1"

            def chat(self, messages, **kwargs):
                return "custom response"

        llm_factory.register("custom", CustomClient)
        client = llm_factory.get_client("custom", api_key="ck")
        assert client.provider_name == "custom"
        assert client.model == "custom-v1"
        assert client.chat([]) == "custom response"

    def test_client_model_override(self):
        """测试模型名称覆盖"""
        client = llm_factory.get_client("openai", api_key="k", model="gpt-3.5-turbo")
        assert client.model == "gpt-3.5-turbo"

    def test_singleton_global_factory(self):
        """全局工厂应为同一实例"""
        from extractor.llm_factory import LLMFactory
        f1 = LLMFactory()
        assert isinstance(llm_factory, LLMFactory)


# ============================
# InfoExtractor 测试
# ============================
class TestInfoExtractor:
    """信息抽取引擎测试"""

    def setup_method(self):
        # 创建一个模拟的LLM客户端
        class MockLLMClient(BaseLLMClient):
            provider_name = "mock"

            @staticmethod
            def default_model():
                return "mock-v1"

            def chat(self, messages, **kwargs):
                # 根据输入返回不同的模拟结果
                user_msg = messages[-1]["content"] if messages else ""
                if "天气" in user_msg:
                    return '{"weather": "晴天", "temperature": 25}'
                if "公司" in user_msg:
                    return '{"company": "AI科技", "industry": "人工智能", "location": "北京"}'
                return '{"entities": [], "summary": "无法识别内容"}'

        self.mock_client = MockLLMClient(api_key="mock_key")
        self.extractor = InfoExtractor(client=self.mock_client)

    def test_extract_success(self):
        result = self.extractor.extract("今天天气怎么样")
        assert result["success"] is True
        assert result["data"]["weather"] == "晴天"

    def test_extract_company_info(self):
        result = self.extractor.extract("这家公司成立于2020年")
        assert result["success"] is True
        assert result["data"]["company"] == "AI科技"

    def test_extract_unknown(self):
        result = self.extractor.extract("随机文本")
        assert result["success"] is True
        assert result["data"]["entities"] == []

    def test_register_custom_prompt(self):
        custom_template = "分析以下文本: {text}，输出JSON"
        self.extractor.register_prompt("analysis", custom_template)
        assert self.extractor.get_prompt("analysis") == custom_template

    def test_get_default_prompt(self):
        prompt = self.extractor.get_prompt("nonexistent")
        assert prompt == DEFAULT_EXTRACTION_PROMPT

    def test_extract_with_custom_prompt(self):
        self.extractor.register_prompt("custom", "请处理: {text}")
        result = self.extractor.extract("今天天气怎么样", prompt_name="custom")
        assert result["success"] is True

    def test_batch_extract(self):
        texts = ["今天天气怎么样", "这家AI公司", "随机内容"]
        results = self.extractor.batch_extract(texts)
        assert len(results) == 3
        assert all(r["success"] for r in results)

    def test_batch_extract_dedup(self):
        """测试批量抽取去重"""
        texts = ["天气", "公司", "天气"]  # 第1和第3相同
        results = self.extractor.batch_extract(texts, dedup=True)
        assert len(results) == 3
        assert results[0]["success"] is True
        assert results[2].get("skipped") is True  # 重复内容被跳过

    def test_extract_contains_md5(self):
        result = self.extractor.extract("测试文本")
        assert "content_md5" in result
        assert len(result["content_md5"]) == 32


# ============================
# Prompt模板测试
# ============================
class TestPromptTemplates:
    """Prompt模板测试"""

    def test_default_prompt_contains_placeholder(self):
        assert "{text}" in DEFAULT_EXTRACTION_PROMPT

    def test_generic_kv_prompt(self):
        assert "{text}" in GENERIC_KV_EXTRACTION_PROMPT
        assert "JSON" in GENERIC_KV_EXTRACTION_PROMPT

    def test_prompt_formatting(self):
        """测试Prompt模板格式化"""
        formatted = DEFAULT_EXTRACTION_PROMPT.replace("{text}", "测试内容")
        assert "测试内容" in formatted
        assert "{text}" not in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
