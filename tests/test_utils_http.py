# -*- coding: utf-8 -*-
"""utils.http_client 模块单元测试"""
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.http_client import (
    get_random_ua,
    get_default_headers,
    CircuitBreaker,
    CircuitBreakerOpenError,
    HTTPClient,
    MaxRetryExceededError,
    USER_AGENT_POOL,
)


class TestUserAgent:
    """UA池测试"""

    def test_get_random_ua(self):
        """测试获取随机UA"""
        ua = get_random_ua()
        assert isinstance(ua, str)
        assert len(ua) > 0
        assert ua in USER_AGENT_POOL

    def test_get_random_ua_diversity(self):
        """测试UA的随机性（多次调用至少出现不同值）"""
        uas = set()
        for _ in range(50):
            uas.add(get_random_ua())
        # 至少出现2个不同的UA
        assert len(uas) >= 2

    def test_get_default_headers(self):
        """测试默认请求头"""
        headers = get_default_headers()
        assert "User-Agent" in headers
        assert headers["User-Agent"] in USER_AGENT_POOL
        assert "Accept" in headers
        assert "Accept-Language" in headers

    def test_get_default_headers_with_extra(self):
        """测试合并额外请求头"""
        extra = {"X-Custom": "test-value", "Authorization": "Bearer token123"}
        headers = get_default_headers(extra)
        assert headers["X-Custom"] == "test-value"
        assert headers["Authorization"] == "Bearer token123"
        assert "User-Agent" in headers  # 默认头仍然存在


class TestCircuitBreaker:
    """熔断器测试"""

    def test_initial_state_closed(self):
        """初始状态应为CLOSED"""
        cb = CircuitBreaker(name="test", failure_threshold=3, timeout=60)
        assert cb.state == CircuitBreaker.STATE_CLOSED

    def test_circuit_opens_after_failures(self):
        """连续失败达到阈值后应打开熔断"""
        cb = CircuitBreaker(name="test", failure_threshold=3, timeout=60)

        def always_fail():
            raise ValueError("模拟失败")

        # 前2次失败不应熔断
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(always_fail)
        assert cb.state == CircuitBreaker.STATE_CLOSED

        # 第3次失败应触发熔断
        with pytest.raises(ValueError):
            cb.call(always_fail)
        assert cb.state == CircuitBreaker.STATE_OPEN

    def test_circuit_rejects_when_open(self):
        """熔断打开时应拒绝请求"""
        cb = CircuitBreaker(name="test", failure_threshold=1, timeout=60)

        with pytest.raises(ValueError):
            cb.call(lambda: 1 / 0)

        assert cb.state == CircuitBreaker.STATE_OPEN
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not run")

    def test_circuit_half_open_and_recovery(self):
        """测试半开状态恢复"""
        cb = CircuitBreaker(name="test", failure_threshold=1, timeout=0)  # timeout=0立即进入半开

        # 触发熔断
        with pytest.raises(ValueError):
            cb.call(lambda: 1 / 0)
        assert cb.state == CircuitBreaker.STATE_OPEN

        # 成功调用后应从半开恢复
        def success():
            return "ok"

        result = cb.call(success)
        assert result == "ok"
        assert cb.state == CircuitBreaker.STATE_CLOSED

    def test_half_open_fails_back_to_open(self):
        """半开状态失败应重新熔断"""
        cb = CircuitBreaker(name="test", failure_threshold=1, timeout=0)

        # 触发熔断
        with pytest.raises(ValueError):
            cb.call(lambda: 1 / 0)
        assert cb.state == CircuitBreaker.STATE_OPEN

        # 半开状态再次失败
        with pytest.raises(ValueError):
            cb.call(lambda: 1 / 0)
        assert cb.state == CircuitBreaker.STATE_OPEN

    def test_reset(self):
        """测试手动重置"""
        cb = CircuitBreaker(name="test", failure_threshold=1, timeout=60)

        with pytest.raises(ValueError):
            cb.call(lambda: 1 / 0)
        assert cb.state == CircuitBreaker.STATE_OPEN

        cb.reset()
        assert cb.state == CircuitBreaker.STATE_CLOSED


class TestHTTPClient:
    """HTTP客户端测试（不依赖外部服务）"""

    def test_build_url(self):
        """测试URL构建"""
        client = HTTPClient(name="test", base_url="https://api.example.com")
        assert client._build_url("/v1/test") == "https://api.example.com/v1/test"
        assert client._build_url("https://other.com/path") == "https://other.com/path"

    def test_default_retry_config(self):
        """测试默认重试配置"""
        client = HTTPClient(name="test")
        assert client.max_retries >= 1
        assert len(client.retry_intervals) >= client.max_retries

    def test_context_manager(self):
        """测试上下文管理器"""
        with HTTPClient(name="test") as client:
            assert client.name == "test"
        # 退出后session应关闭

    def test_max_retry_exceeded_error(self):
        """测试MaxRetryExceededError异常"""
        error = MaxRetryExceededError("重试耗尽", last_exception=Exception("原始错误"))
        assert "重试耗尽" in str(error)
        assert isinstance(error.last_exception, Exception)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
