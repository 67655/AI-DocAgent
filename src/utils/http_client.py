# -*- coding: utf-8 -*-
"""
HTTP请求工具模块
提供动态UA池、阶梯重试、熔断降级等通用API容错机制
"""
import random
import time
import threading
from typing import Any, Dict, Optional, Callable

import requests

from .config import config
from .logger import get_logger

logger = get_logger(__name__)


# ============================
# 动态UA池
# ============================
USER_AGENT_POOL = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Firefox macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


def get_random_ua() -> str:
    """随机获取一个User-Agent"""
    return random.choice(USER_AGENT_POOL)


def get_default_headers(extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    获取带随机UA的默认请求头

    Args:
        extra_headers: 额外的请求头，会合并到默认头中

    Returns:
        合并后的请求头字典
    """
    headers = {
        "User-Agent": get_random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


# ============================
# 熔断器
# ============================
class CircuitBreaker:
    """
    熔断器 - 当连续失败达到阈值时自动熔断，防止雪崩
    状态：CLOSED(正常) -> OPEN(熔断) -> HALF_OPEN(半开探测) -> CLOSED
    """

    # 熔断状态
    STATE_CLOSED = "closed"       # 正常通行
    STATE_OPEN = "open"           # 熔断拒绝
    STATE_HALF_OPEN = "half_open" # 半开探测

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        timeout: int = 60,
        half_open_max: int = 1,
    ):
        """
        Args:
            name: 熔断器名称
            failure_threshold: 连续失败多少次后熔断
            timeout: 熔断后多久进入半开状态（秒）
            half_open_max: 半开状态最多允许的探测请求数
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_max = half_open_max

        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_count = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """当前熔断状态"""
        return self._state

    def _transition_state(self, new_state: str):
        """状态转换"""
        old_state = self._state
        self._state = new_state
        if new_state == self.STATE_HALF_OPEN:
            self._half_open_count = 0
        if new_state == self.STATE_CLOSED:
            self._failure_count = 0
        logger.info(f"[熔断器:{self.name}] 状态变更: {old_state} -> {new_state}")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        受熔断器保护的函数调用

        Args:
            func: 要执行的函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerOpenError: 熔断器打开时拒绝请求
        """
        with self._lock:
            if self._state == self.STATE_OPEN:
                if time.time() - self._last_failure_time >= self.timeout:
                    self._transition_state(self.STATE_HALF_OPEN)
                else:
                    raise CircuitBreakerOpenError(
                        f"熔断器 [{self.name}] 已打开，"
                        f"{int(self.timeout - (time.time() - self._last_failure_time))}秒后可重试"
                    )

            if self._state == self.STATE_HALF_OPEN:
                if self._half_open_count >= self.half_open_max:
                    raise CircuitBreakerOpenError(
                        f"熔断器 [{self.name}] 半开状态已达到探测上限"
                    )
                self._half_open_count += 1

        try:
            result = func(*args, **kwargs)
            with self._lock:
                if self._state == self.STATE_HALF_OPEN:
                    self._transition_state(self.STATE_CLOSED)
                elif self._state == self.STATE_CLOSED:
                    self._failure_count = 0
            return result
        except Exception:
            with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                if (
                    self._state == self.STATE_CLOSED
                    and self._failure_count >= self.failure_threshold
                ):
                    self._transition_state(self.STATE_OPEN)
                elif self._state == self.STATE_HALF_OPEN:
                    self._transition_state(self.STATE_OPEN)
            raise

    def reset(self):
        """手动重置熔断器到关闭状态"""
        with self._lock:
            self._transition_state(self.STATE_CLOSED)


class CircuitBreakerOpenError(Exception):
    """熔断器打开异常"""
    pass


# ============================
# HTTP客户端（含阶梯重试+熔断）
# ============================
class HTTPClient:
    """
    通用HTTP请求客户端
    - 动态UA轮换
    - 阶梯重试（1s, 3s, 5s, 10s...）
    - 熔断保护
    - 超时控制
    """

    def __init__(
        self,
        name: str = "default",
        base_url: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_intervals: Optional[list] = None,
        timeout: int = 30,
        circuit_breaker_threshold: Optional[int] = None,
    ):
        """
        Args:
            name: 客户端名称（用于日志标识）
            base_url: 基础URL前缀
            max_retries: 最大重试次数（默认使用配置值）
            retry_intervals: 自定义重试间隔列表（秒），如 [1, 3, 5, 10, 30]
            timeout: 请求超时时间（秒）
            circuit_breaker_threshold: 熔断阈值（默认使用配置值的一半）
        """
        self.name = name
        self.base_url = base_url or ""
        self.max_retries = max_retries or config.MAX_RETRY_COUNT
        self.retry_intervals = retry_intervals or [1, 3, 5, 10, 30]
        self.timeout = timeout

        # 确保重试间隔足够覆盖最大重试次数
        while len(self.retry_intervals) < self.max_retries:
            self.retry_intervals.append(self.retry_intervals[-1] * 2)

        cb_threshold = circuit_breaker_threshold or max(3, config.MAX_RETRY_COUNT)
        self.circuit_breaker = CircuitBreaker(
            name=f"http_{name}",
            failure_threshold=cb_threshold,
            timeout=60,
        )

        # 创建持久化Session用于连接复用
        self.session = requests.Session()

    def _build_url(self, path: str) -> str:
        """构建完整URL"""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def _do_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Any] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        **kwargs,
    ) -> requests.Response:
        """执行单次HTTP请求（由熔断器保护）"""
        full_url = self._build_url(url)
        req_headers = get_default_headers(headers)

        logger.debug(f"[HTTP:{self.name}] {method.upper()} {full_url}")

        response = self.session.request(
            method=method,
            url=full_url,
            params=params,
            data=data,
            json=json,
            headers=req_headers,
            timeout=self.timeout,
            **kwargs,
        )
        return response

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Any] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        raise_on_status: bool = True,
        **kwargs,
    ) -> requests.Response:
        """
        执行HTTP请求（带阶梯重试+熔断保护）

        Args:
            method: HTTP方法 (GET/POST/PUT/DELETE)
            url: 请求URL或路径
            params: URL查询参数
            data: 请求体数据
            json: JSON请求体
            headers: 额外的请求头
            raise_on_status: 是否在非2xx状态码时抛出异常

        Returns:
            requests.Response 对象

        Raises:
            CircuitBreakerOpenError: 熔断器打开
            MaxRetryExceededError: 超过最大重试次数
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                # 通过熔断器执行请求
                response = self.circuit_breaker.call(
                    self._do_request, method, url, params, data, json, headers, **kwargs
                )

                if raise_on_status and response.status_code >= 400:
                    raise HTTPStatusError(
                        f"HTTP {response.status_code}: {response.reason}",
                        status_code=response.status_code,
                        response=response,
                    )

                # 成功则重置熔断器
                self.circuit_breaker.reset()
                return response

            except (CircuitBreakerOpenError, HTTPStatusError):
                raise

            except requests.RequestException as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = self.retry_intervals[attempt] if attempt < len(self.retry_intervals) else 5
                    logger.warning(
                        f"[HTTP:{self.name}] 请求失败 (第{attempt + 1}次)，"
                        f"{wait_time}秒后重试: {url} | 错误: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[HTTP:{self.name}] 请求失败，已达最大重试次数({self.max_retries}): "
                        f"{url} | 错误: {e}"
                    )

        raise MaxRetryExceededError(
            f"请求 {url} 在 {self.max_retries} 次重试后仍失败",
            last_exception=last_exception,
        )

    def get(self, url: str, params: Optional[Dict] = None, **kwargs) -> requests.Response:
        """GET请求"""
        return self.request("GET", url, params=params, **kwargs)

    def post(self, url: str, data: Optional[Any] = None, json: Optional[Dict] = None, **kwargs) -> requests.Response:
        """POST请求"""
        return self.request("POST", url, data=data, json=json, **kwargs)

    def close(self):
        """关闭HTTP客户端"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class HTTPStatusError(Exception):
    """HTTP状态码异常"""
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class MaxRetryExceededError(Exception):
    """超过最大重试次数异常"""
    def __init__(self, message, last_exception=None):
        super().__init__(message)
        self.last_exception = last_exception
