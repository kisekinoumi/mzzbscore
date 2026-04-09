# src/extractors/twitter.py
# Twitter粉丝数据提取器模块 — 基于 Scweet 实现

import logging
import time
from typing import Optional

try:
    from Scweet import Scweet, ScweetConfig
    from Scweet import ScweetError, AccountPoolExhausted, AuthError, NetworkError
    SCWEET_AVAILABLE = True
except ImportError:
    SCWEET_AVAILABLE = False
    logging.warning("Scweet库未安装，Twitter粉丝数获取功能将被禁用。请运行: pip install -U Scweet")

from utils.core.twitter_config import get_twitter_config
from utils.network.proxy_config import get_global_proxy


class TwitterFollowersAPI:
    """Twitter粉丝数据获取API封装（基于Scweet）"""

    def __init__(self):
        self._scweet: Optional["Scweet"] = None
        self.is_initialized = False
        self.last_error: Optional[str] = None
        self.twitter_config = get_twitter_config()

        # 内存缓存：username -> (followers_count, expire_timestamp)
        self._cache: dict = {}

        # 请求配置
        self.request_config = {
            'max_retry': 3,
            'retry_delay': 2,
        }

    def _should_skip(self) -> bool:
        """检查是否应该跳过Twitter功能"""
        if not SCWEET_AVAILABLE:
            logging.debug("Scweet库未安装，跳过Twitter粉丝数获取")
            return True

        # 重新获取最新的配置状态
        from utils.core.twitter_config import get_twitter_config
        current_config = get_twitter_config()
        if not current_config.is_enabled():
            logging.debug("Twitter功能未启用或配置验证失败，跳过粉丝数获取")
            return True

        return False

    def _initialize(self) -> bool:
        """初始化 Scweet 实例"""
        if self.is_initialized and self._scweet is not None:
            return True

        if self._should_skip():
            return False

        try:
            account_info = self.twitter_config.get_account_info()
            if not account_info:
                logging.warning("未配置Twitter账号信息")
                return False

            auth_token = account_info.get('auth_token')
            if not auth_token:
                logging.warning("Twitter auth_token 为空")
                return False

            # 获取代理配置
            proxy_config = get_global_proxy()
            proxy_url = None
            if proxy_config:
                proxy_url = proxy_config.get('http')
                logging.info(f"Twitter API将使用代理: {proxy_url}")

            # 构建 ScweetConfig
            config_kwargs = {
                'daily_requests_limit': 5000,
                'requests_per_min': 100
            }
            if proxy_url:
                config_kwargs['proxy'] = proxy_url
                
            # 关闭 Scweet 自身的详细日志（由项目的 logging 接管）
            scweet_config = ScweetConfig(**config_kwargs) if config_kwargs else None

            if scweet_config:
                self._scweet = Scweet(auth_token=auth_token, config=scweet_config)
            else:
                self._scweet = Scweet(auth_token=auth_token)

            self.is_initialized = True
            logging.info("Scweet Twitter API 初始化成功")
            return True

        except Exception as e:
            self.last_error = str(e)
            logging.error(f"Scweet 初始化失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 缓存相关
    # ------------------------------------------------------------------

    def _is_cache_valid(self, username: str) -> bool:
        if username not in self._cache:
            return False
        _, expire_time = self._cache[username]
        return time.time() < expire_time

    def _get_from_cache(self, username: str) -> Optional[int]:
        if self._is_cache_valid(username):
            count, _ = self._cache[username]
            logging.debug(f"从缓存获取 @{username} 的粉丝数: {count}")
            return count
        return None

    def _save_to_cache(self, username: str, followers_count: int) -> None:
        expire_time = time.time() + 24 * 3600  # 24 小时有效
        self._cache[username] = (followers_count, expire_time)
        logging.debug(f"缓存 @{username} 的粉丝数: {followers_count}")

    # ------------------------------------------------------------------
    # 核心获取逻辑
    # ------------------------------------------------------------------

    def get_user_followers(self, username: str) -> Optional[int]:
        """
        获取 Twitter 用户粉丝数（同步接口）
        Args:
            username: Twitter 用户名（不含 @ 符号）
        Returns:
            int or None: 粉丝数，失败时返回 None
        """
        if self._should_skip():
            return None

        clean_username = username.lstrip('@')
        if not clean_username:
            logging.warning("Twitter用户名为空")
            return None

        # 检查缓存
        cached = self._get_from_cache(clean_username)
        if cached is not None:
            return cached

        # 确保已初始化
        if not self._initialize():
            return None

        try:
            logging.info(f"正在获取 @{clean_username} 的粉丝数...")
            # Scweet.get_user_info 是同步方法，返回 list[dict]
            results = self._scweet.get_user_info([clean_username])

            if not results:
                logging.warning(f"无法获取 @{clean_username} 的用户信息（返回为空）")
                return None

            user_info = results[0]
            followers_count = user_info.get('followers_count')

            if followers_count is None:
                logging.warning(f"@{clean_username} 的用户信息中没有 followers_count 字段")
                return None

            followers_count = int(followers_count)
            logging.info(f"@{clean_username} 的粉丝数: {followers_count:,}")
            self._save_to_cache(clean_username, followers_count)
            return followers_count

        except AuthError as e:
            logging.error(f"Twitter 认证失败，请刷新 auth_token: {e}")
            # 认证失败时禁用功能，避免后续每个动画都触发同样错误
            self.twitter_config.disable_with_reason(f"auth_token 已失效: {e}")
            return None
        except AccountPoolExhausted as e:
            logging.warning(f"Twitter 账号已达到限额或冷却中: {e}")
            return None
        except NetworkError as e:
            logging.error(f"Twitter 网络连接失败: {e}")
            return None
        except Exception as e:
            logging.error(f"获取 @{clean_username} 粉丝数时出错: {e}")
            return None

    def get_followers_with_retry(self, username: str) -> Optional[int]:
        """
        带重试机制的粉丝数获取
        Args:
            username: Twitter 用户名
        Returns:
            int or None: 粉丝数，失败时返回 None
        """
        if self._should_skip():
            return None

        max_retry = self.request_config.get('max_retry', 3)
        retry_delay = self.request_config.get('retry_delay', 2)

        for attempt in range(max_retry):
            try:
                result = self.get_user_followers(username)
                if result is not None:
                    return result

                if attempt < max_retry - 1:
                    logging.info(
                        f"获取 @{username} 粉丝数失败，{retry_delay}秒后重试 "
                        f"({attempt + 1}/{max_retry})"
                    )
                    time.sleep(retry_delay)

            except Exception as e:
                logging.error(f"第 {attempt + 1} 次尝试获取 @{username} 粉丝数失败: {e}")
                if attempt < max_retry - 1:
                    time.sleep(retry_delay)

        logging.error(f"经过 {max_retry} 次尝试后，仍无法获取 @{username} 粉丝数")
        return None


class TwitterFollowersHelper:
    """Twitter粉丝数获取助手类（单例工厂 + 格式化工具）"""

    _api_instance: Optional[TwitterFollowersAPI] = None

    @staticmethod
    def format_followers_count(followers_count) -> str:
        """
        格式化粉丝数为千分位格式
        Args:
            followers_count: 粉丝数（数字或错误字符串）
        Returns:
            str: 格式化后的粉丝数字符串
        """
        if not followers_count:
            return ""

        error_messages = ['获取失败', '获取出错', '配置未成功', 'Request failed', 'Parse error',
                          '网络不可用', '认证失败']
        if isinstance(followers_count, str) and any(msg in followers_count for msg in error_messages):
            return followers_count

        try:
            if isinstance(followers_count, str):
                clean_count = followers_count.replace(',', '').replace(' ', '')
                followers_int = int(clean_count)
            else:
                followers_int = int(followers_count)
            return f"{followers_int:,}"
        except (ValueError, TypeError):
            return str(followers_count)

    @classmethod
    def get_api_instance(cls) -> TwitterFollowersAPI:
        """获取 API 实例（单例模式）"""
        if cls._api_instance is None:
            cls._api_instance = TwitterFollowersAPI()
        return cls._api_instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置 API 实例（配置变更后调用）"""
        cls._api_instance = None
        logging.debug("TwitterFollowersAPI 实例已重置")

    @classmethod
    def get_followers_count(cls, username: str) -> Optional[int]:
        """
        获取 Twitter 用户粉丝数
        Args:
            username: Twitter 用户名
        Returns:
            int or None: 粉丝数，失败时返回 None
        """
        if not username:
            return None
        api = cls.get_api_instance()
        return api.get_followers_with_retry(username)

    @classmethod
    def extract_username_from_url(cls, twitter_url: str) -> Optional[str]:
        """
        从 Twitter URL 中提取用户名
        Args:
            twitter_url: Twitter URL
        Returns:
            str or None: 用户名，失败时返回 None
        """
        if not twitter_url:
            return None

        import re
        patterns = [
            r'twitter\.com/([^/?]+)',
            r'x\.com/([^/?]+)',
            r'@(\w+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, twitter_url, re.IGNORECASE)
            if match:
                username = match.group(1)
                invalid = ['home', 'search', 'explore', 'notifications', 'messages',
                           'i', 'intent', 'settings', 'help', 'about']
                if username.lower() not in invalid:
                    return username
        return None

    @classmethod
    def get_followers_from_url(cls, twitter_url: str) -> Optional[int]:
        """
        从 Twitter URL 获取粉丝数
        Args:
            twitter_url: Twitter URL
        Returns:
            int or None: 粉丝数，失败时返回 None
        """
        username = cls.extract_username_from_url(twitter_url)
        if username:
            return cls.get_followers_count(username)
        return None