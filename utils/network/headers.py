# utils/network/headers.py
# 网络请求Headers统一配置管理

import hashlib
import random
from typing import Dict, Optional


class RequestHeaders:
    """网络请求Headers配置类"""

    # 真实浏览器 UA 池（覆盖主流桌面/移动系统与浏览器版本，按条目+站点稳定哈希选取）
    USER_AGENT_POOL = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    )

    # 通用默认User-Agent
    DEFAULT_USER_AGENT = USER_AGENT_POOL[0]

    # 基础headers组合
    BASE_HEADERS = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "ja-JP,ja;q=0.9,zh-CN;q=0.8,zh;q=0.7,en;q=0.6",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # JSON API专用headers
    JSON_API_HEADERS = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "ja-JP,ja;q=0.9,zh-CN;q=0.8,en;q=0.7",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # HTML页面爬取专用headers
    HTML_HEADERS = {
        **BASE_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    }

    # GraphQL专用headers
    GRAPHQL_HEADERS = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    @classmethod
    def pick_user_agent(
        cls,
        site_code: Optional[str] = None,
        item_key: Optional[str] = None,
    ) -> str:
        """
        按 (item_key, site_code) 稳定哈希选取 UA，避免同一作品对同站点请求时 UA 频繁跳变触发风控。
        """
        key = f"{item_key or ''}|{site_code or ''}"
        if not key.strip("|"):
            return random.choice(cls.USER_AGENT_POOL)
        digest = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
        return cls.USER_AGENT_POOL[digest % len(cls.USER_AGENT_POOL)]

    @classmethod
    def get_bangumi_headers(cls) -> Dict[str, str]:
        """获取Bangumi API请求headers"""
        return cls.JSON_API_HEADERS.copy()

    @classmethod
    def get_anilist_headers(cls) -> Dict[str, str]:
        """获取AniList GraphQL请求headers"""
        return cls.GRAPHQL_HEADERS.copy()

    @classmethod
    def get_myanimelist_headers(cls) -> Dict[str, str]:
        """获取MyAnimeList API请求headers"""
        return cls.JSON_API_HEADERS.copy()

    @classmethod
    def get_myanimelist_api_headers(
        cls,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, str]:
        """获取带鉴权信息的MyAnimeList API请求headers"""
        headers = cls.get_myanimelist_headers()
        if client_id:
            headers["X-MAL-CLIENT-ID"] = client_id
        if access_token:
            token = (
                access_token
                if access_token.lower().startswith("bearer ")
                else f"Bearer {access_token}"
            )
            headers["Authorization"] = token
        return headers

    @classmethod
    def get_filmarks_headers(cls) -> Dict[str, str]:
        """获取Filmarks页面爬取headers"""
        headers = cls.HTML_HEADERS.copy()
        headers["Accept-Language"] = "ja-JP,ja;q=0.9,en;q=0.5"
        return headers

    @classmethod
    def get_filmarks_api_headers(cls) -> Dict[str, str]:
        """获取Filmarks移动端API请求headers"""
        return {
            "User-Agent": "Filmarks/10.24.0 (Android 14)",
            "X-App-Version": "10.24.0",
            "X-Platform": "android",
            "X-From": "filmarks-anime-app",
            "Accept": "application/json",
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.5",
        }

    @classmethod
    def get_custom_headers(
        cls,
        accept: Optional[str] = None,
        content_type: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """获取自定义headers"""
        headers = cls.BASE_HEADERS.copy()
        if accept:
            headers["Accept"] = accept
        if content_type:
            headers["Content-Type"] = content_type
        if additional_headers:
            headers.update(additional_headers)
        return headers


# 为了向后兼容，提供常用的headers常量
BANGUMI_HEADERS = RequestHeaders.get_bangumi_headers()
ANILIST_HEADERS = RequestHeaders.get_anilist_headers()
MYANIMELIST_HEADERS = RequestHeaders.get_myanimelist_headers()
FILMARKS_HEADERS = RequestHeaders.get_filmarks_headers()
FILMARKS_API_HEADERS = RequestHeaders.get_filmarks_api_headers()

__all__ = [
    "RequestHeaders",
    "BANGUMI_HEADERS",
    "ANILIST_HEADERS",
    "MYANIMELIST_HEADERS",
    "FILMARKS_HEADERS",
    "FILMARKS_API_HEADERS",
]
