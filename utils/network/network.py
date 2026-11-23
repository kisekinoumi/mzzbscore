# utils/network/network.py
# 存放网络请求相关的工具函数（线程本地连接池 + 站点级自适应限流 + 智能重试与缓存）

import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Collection, Dict, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

from .headers import RequestHeaders
from .proxy_config import get_global_proxy

# 常量定义
MAX_RETRIES = 3
REQUEST_TIMEOUT = 12  # 单次请求超时时间（秒）
DEFAULT_USER_AGENT = RequestHeaders.DEFAULT_USER_AGENT
MAX_CACHE_ENTRIES = 512

# 不应盲目退避重试的客户端状态码（429 单独走限流重试逻辑）
NON_RETRYABLE_CLIENT_STATUSES = frozenset({400, 401, 403, 404, 410, 422})

# 各站点默认最小礼貌请求间隔（秒）——参照 anime-score-aggregator 限流设计
DEFAULT_SITE_MIN_INTERVALS: Dict[str, float] = {
    "anilist": 60.0 / 88.0,        # AniList 健康期 ~90 req/min，留余量按 88/min 平滑
    "bangumi": 0.20,               # Bangumi API 礼貌间隔
    "myanimelist_api": 0.25,       # MAL 官方 API 礼貌间隔
    "myanimelist_web": 0.45,       # MAL 网页搜索/详情防 WAF 间隔
    "filmarks_api": 0.20,          # Filmarks 移动 API 间隔
    "filmarks_web": 0.45,          # Filmarks 网页兜底防 WAF 间隔
}

# 线程本地 Session 存储与全局 Session 追踪（便于退出时释放）
_SESSION_LOCAL = threading.local()
_TRACKED_SESSIONS_LOCK = threading.Lock()
_TRACKED_SESSIONS = []

# 内存缓存与锁
_CACHE_LOCK = threading.Lock()
_request_cache: Dict[str, Any] = {}


class SiteRateLimiter:
    """进程内线程安全的站点级请求节流与共享冷却控制器"""

    def __init__(self):
        self._lock = threading.Lock()
        self._next_request_at: Dict[str, float] = {}
        self._cooldown_until: Dict[str, float] = {}
        self._temp_intervals: Dict[str, float] = {}  # site_code -> (interval, expire_mono)

    def reset(self) -> None:
        with self._lock:
            self._next_request_at.clear()
            self._cooldown_until.clear()
            self._temp_intervals.clear()

    def _effective_interval(self, site_code: str, now_mono: float) -> float:
        base = DEFAULT_SITE_MIN_INTERVALS.get(site_code, 0.0)
        temp = self._temp_intervals.get(site_code)
        if temp is not None:
            interval, expire_at = temp
            if now_mono < expire_at:
                return max(base, interval)
            self._temp_intervals.pop(site_code, None)
        return base

    def wait_turn(self, site_code: Optional[str], jitter: float = 0.2) -> None:
        """原子预约该站点的下一次请求窗口，并在锁外睡眠"""
        if not site_code:
            return

        with self._lock:
            now = time.monotonic()
            cooldown = self._cooldown_until.get(site_code, 0.0)
            interval = self._effective_interval(site_code, now)
            prev_next = self._next_request_at.get(site_code, 0.0)

            start_at = max(now, cooldown, prev_next)
            if interval > 0:
                delta = interval * jitter
                paced_interval = max(0.0, interval + random.uniform(-delta, delta))
                self._next_request_at[site_code] = start_at + paced_interval
            wait_seconds = max(0.0, start_at - now)

        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def set_cooldown(self, site_code: Optional[str], seconds: float) -> None:
        """延长站点全局冷却窗口（后到的短 Retry-After 不会覆盖已有的更长冷却）"""
        if not site_code or seconds <= 0:
            return
        with self._lock:
            target = time.monotonic() + seconds
            current = self._cooldown_until.get(site_code, 0.0)
            if target > current:
                self._cooldown_until[site_code] = target

    def set_temporary_rate_limit(
        self,
        site_code: Optional[str],
        requests_per_minute: int,
        ttl_seconds: float = 300.0,
    ) -> None:
        """根据外站响应头（如 AniList 降级期 30 req/min）临时调慢站点请求速率"""
        if not site_code or requests_per_minute <= 0:
            return
        interval = 60.0 / float(requests_per_minute)
        with self._lock:
            self._temp_intervals[site_code] = (interval, time.monotonic() + ttl_seconds)

    def observe_response_headers(self, site_code: Optional[str], headers: Dict[str, str]) -> None:
        """观察响应头中的限流信号（如 AniList X-RateLimit-Limit / X-RateLimit-Remaining）"""
        if site_code != "anilist" or not headers:
            return

        lower_map = {k.lower(): v for k, v in headers.items()}
        raw_limit = lower_map.get("x-ratelimit-limit")
        if raw_limit:
            try:
                limit_val = int(raw_limit)
                if 0 < limit_val < 88:
                    self.set_temporary_rate_limit("anilist", max(1, limit_val - 2), ttl_seconds=300.0)
            except (TypeError, ValueError):
                pass

        raw_remaining = lower_map.get("x-ratelimit-remaining")
        if raw_remaining:
            try:
                remaining_val = int(raw_remaining)
                if remaining_val <= 2:
                    self.set_cooldown("anilist", 2.5)
            except (TypeError, ValueError):
                pass


_rate_limiter = SiteRateLimiter()


def infer_site_code(url: str) -> Optional[str]:
    """从请求 URL 推断站点标识，用于自动匹配限流与 UA 策略"""
    if not url:
        return None
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return None

    if "anilist.co" in host:
        return "anilist"
    if host in ("api.bgm.tv", "bgm.tv", "www.bgm.tv", "bangumi.tv", "www.bangumi.tv"):
        return "bangumi"
    if host == "api.myanimelist.net":
        return "myanimelist_api"
    if "myanimelist.net" in host:
        return "myanimelist_web"
    if host == "api.filmarks.com":
        return "filmarks_api"
    if "filmarks.com" in host:
        return "filmarks_web"
    return host or None


def parse_retry_after(headers: Optional[Dict[str, str]], default_seconds: float = 5.0) -> float:
    """解析 Retry-After 头（支持秒数与 HTTP-date 两种标准格式）"""
    if not headers:
        return default_seconds
    raw = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if not raw:
        return default_seconds
    raw_str = str(raw).strip()
    try:
        delay = float(raw_str)
        if 0 <= delay < 300:
            return max(1.0, delay)
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(raw_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = (dt - datetime.now(timezone.utc)).total_seconds()
            return min(max(1.0, delta), 120.0)
        except Exception:
            pass
    return default_seconds


def _get_http_session() -> requests.Session:
    """获取当前线程的 requests.Session（复用 Keep-Alive 连接池）"""
    pid = os.getpid()
    session = getattr(_SESSION_LOCAL, "session", None)
    session_pid = getattr(_SESSION_LOCAL, "pid", None)
    if session is None or session_pid != pid:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _SESSION_LOCAL.session = session
        _SESSION_LOCAL.pid = pid
        with _TRACKED_SESSIONS_LOCK:
            _TRACKED_SESSIONS.append(session)
    return session


def _reset_current_thread_session() -> None:
    """发生底层连接/SSL异常时重置当前线程 Session，丢弃失效连接池句柄"""
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is not None:
        try:
            session.close()
        except Exception:
            pass
    _SESSION_LOCAL.session = None
    _SESSION_LOCAL.pid = None


def close_all_http_sessions() -> None:
    """关闭所有工作线程创建的 HTTP Session"""
    with _TRACKED_SESSIONS_LOCK:
        sessions = list(_TRACKED_SESSIONS)
        _TRACKED_SESSIONS.clear()
    for session in sessions:
        try:
            session.close()
        except Exception:
            pass
    _SESSION_LOCAL.session = None
    _SESSION_LOCAL.pid = None


def clear_request_cache() -> None:
    """清空内存请求缓存"""
    with _CACHE_LOCK:
        _request_cache.clear()


def _build_cache_key(method: str, url: str, params: Any, data: Any) -> str:
    try:
        params_str = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        params_str = str(params)
    try:
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        data_str = str(data)
    return f"{method.upper()}:{url}:{params_str}:{data_str}"


def fetch_data_with_retry(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    use_cache: bool = True,
    cache_ttl: int = 300,
    site_code: Optional[str] = None,
    item_key: Optional[str] = None,
    allow_error_statuses: Optional[Collection[int]] = None,
) -> Optional[requests.Response]:
    """
    带有连接池复用、站点自适应节流、智能状态码分流与缓存的 HTTP 请求函数。

    Args:
        url: 请求 URL
        params: 查询参数
        data: POST JSON 请求体
        method: 'GET' 或 'POST'
        headers: 自定义请求头
        use_cache: 是否启用内存缓存（对只读 GET/POST 查询有效）
        cache_ttl: 缓存有效期（秒）
        site_code: 可选站点标识（不传则按 URL 自动识别）
        item_key: 可选条目标识（用于稳定哈希选取 User-Agent）
        allow_error_statuses: 允许直接返回给调用方自行判断的非 2xx 状态码集合

    Returns:
        requests.Response 或 None
    """
    method_upper = (method or "GET").upper()
    resolved_site = site_code or infer_site_code(url)
    allowed_statuses = set(allow_error_statuses or ())

    final_headers = dict(headers) if headers else {}
    if "User-Agent" not in final_headers:
        final_headers["User-Agent"] = RequestHeaders.pick_user_agent(
            site_code=resolved_site,
            item_key=item_key or url,
        )

    cache_key = _build_cache_key(method_upper, url, params, data)
    if use_cache:
        with _CACHE_LOCK:
            cache_entry = _request_cache.get(cache_key)
            if cache_entry is not None:
                cache_time, cached_response = cache_entry
                if time.time() - cache_time < cache_ttl:
                    logging.debug(f"Using cached response for {url}")
                    return cached_response
                _request_cache.pop(cache_key, None)

    proxies = get_global_proxy()
    if proxies:
        logging.debug(f"Using proxy for {url}: {proxies.get('http', 'N/A')}")

    logging.info(f"Fetching data from {url} with method {method_upper}")

    for attempt in range(MAX_RETRIES):
        _rate_limiter.wait_turn(resolved_site)
        session = _get_http_session()

        try:
            if method_upper == "GET":
                response = session.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                    headers=final_headers,
                    proxies=proxies,
                )
            elif method_upper == "POST":
                response = session.post(
                    url,
                    params=params,
                    json=data,
                    timeout=REQUEST_TIMEOUT,
                    headers=final_headers,
                    proxies=proxies,
                )
            else:
                raise ValueError(f"Unsupported method: {method}")

            _rate_limiter.observe_response_headers(resolved_site, dict(response.headers))

            # 429 限流处理：同步共享站点冷却并按 Retry-After 退避
            if response.status_code == 429:
                if resolved_site == "anilist":
                    _rate_limiter.set_temporary_rate_limit("anilist", 28, ttl_seconds=300.0)
                fallback_wait = float(2 ** attempt * 4)
                wait_time = parse_retry_after(dict(response.headers), default_seconds=fallback_wait)
                _rate_limiter.set_cooldown(resolved_site, wait_time)
                if attempt < MAX_RETRIES - 1:
                    logging.warning(
                        f"Received 429 Too Many Requests from {resolved_site or url}. "
                        f"Waiting for {wait_time:.1f} seconds before retrying..."
                    )
                    time.sleep(wait_time)
                    continue
                if 429 in allowed_statuses:
                    return response
                logging.error(f"Rate limit persisted after {MAX_RETRIES} attempts for {url}.")
                return None

            # 5xx 服务端临时故障：指数退避重试
            if response.status_code >= 500:
                if attempt < MAX_RETRIES - 1:
                    wait_time = min(2 ** attempt * 2.5, 10.0) + random.uniform(0.0, 0.5)
                    logging.warning(
                        f"Received server error {response.status_code} for {url}. "
                        f"Waiting for {wait_time:.1f} seconds before retrying..."
                    )
                    time.sleep(wait_time)
                    continue
                if response.status_code in allowed_statuses:
                    return response
                logging.error(f"Server error {response.status_code} persisted for {url}.")
                return None

            # 确定性 4xx 客户端错误（如 404 / 401 / 403 / 400）：不盲目睡眠重试
            if response.status_code in NON_RETRYABLE_CLIENT_STATUSES:
                if response.status_code in allowed_statuses:
                    return response
                logging.warning(
                    f"Client status {response.status_code} for {url} (non-retryable)."
                )
                return None

            response.raise_for_status()

            if use_cache and response.status_code == 200:
                with _CACHE_LOCK:
                    if len(_request_cache) >= MAX_CACHE_ENTRIES:
                        oldest_key = next(iter(_request_cache))
                        _request_cache.pop(oldest_key, None)
                    _request_cache[cache_key] = (time.time(), response)

            return response

        except requests.exceptions.ProxyError as e:
            _reset_current_thread_session()
            if proxies and attempt == 0:
                logging.warning(f"Proxy error for {url}, trying direct connection: {e}")
                proxies = None
                continue
            wait_time = min(2 ** attempt * 2.5, 8.0)
            logging.warning(
                f"Proxy error for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}."
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
        except requests.exceptions.Timeout as e:
            _reset_current_thread_session()
            if proxies and attempt == MAX_RETRIES - 2 and resolved_site in ("bangumi", "filmarks_api"):
                logging.warning(f"Proxy timeout for {url}, falling back to direct connection on final retry.")
                proxies = None
                continue
            wait_time = min(2 ** attempt * 2.5, 8.0)
            logging.warning(
                f"Request timed out for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}."
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
        except requests.exceptions.ConnectionError as e:
            _reset_current_thread_session()
            if proxies and attempt == MAX_RETRIES - 2 and resolved_site in ("bangumi", "filmarks_api"):
                logging.warning(f"Proxy connection/SSL error for {url}, falling back to direct connection on final retry.")
                proxies = None
                continue
            wait_time = min(2 ** attempt * 2.0, 8.0)
            logging.warning(
                f"Connection error for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}."
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            wait_time = min(2 ** attempt * 2.5, 8.0)
            logging.warning(
                f"Request failed for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}."
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
            else:
                logging.error(f"Max retries reached for {url}. Giving up.")
                return None

    logging.error(f"All attempts failed for {url}.")
    return None
