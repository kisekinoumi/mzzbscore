# src/extractors/twitter.py
# Twitter粉丝数据提取器模块

import logging
import asyncio
import time
from typing import Optional, Dict, Any
from pathlib import Path

try:
    from twscrape import API, gather
    TWSCRAPE_AVAILABLE = True
except ImportError:
    TWSCRAPE_AVAILABLE = False
    logging.warning("twscrape库未安装，Twitter粉丝数获取功能将被禁用")

from utils.core.twitter_config import get_twitter_config


class TwitterFollowersAPI:
    """Twitter粉丝数据获取API封装"""
    
    def __init__(self):
        self.api = None
        self.is_initialized = False
        self.last_error = None
        self.twitter_config = get_twitter_config()
        
        # 设置twscrape的日志级别，避免详细日志干扰输出
        try:
            from loguru import logger
            logger.remove()  # 移除默认的日志配置
            logger.add(lambda msg: None, level="ERROR")  # 只记录错误级别的日志
        except (ImportError, Exception):
            pass  # 如果loguru不可用或设置失败，忽略
        
        # 缓存
        self._cache = {}
        self._cache_expire = {}
        
        # 请求配置（固定值）
        self.request_config = {
            'timeout': 10,
            'max_retry': 3,
            'retry_delay': 1,
        }
        
    def _should_skip(self) -> bool:
        """检查是否应该跳过Twitter功能"""
        if not TWSCRAPE_AVAILABLE:
            logging.debug("twscrape库未安装，跳过Twitter粉丝数获取")
            return True
        
        # 重新获取最新的配置状态    
        from utils.core.twitter_config import get_twitter_config
        current_config = get_twitter_config()
        if not current_config.is_enabled():
            logging.debug("Twitter功能未启用或配置验证失败，跳过粉丝数获取")
            return True
            
        return False
    
    async def _initialize_api(self) -> bool:
        """初始化twscrape API"""
        if self.is_initialized:
            return True
            
        if self._should_skip():
            return False
            
        try:
            self.api = API()
            
            # 获取Cookies配置
            account_info = self.twitter_config.get_account_info()
            if not account_info:
                logging.warning("未配置Twitter Cookies信息")
                return False
            
            cookies_str = account_info.get('cookies')
            if not cookies_str:
                logging.warning("Twitter Cookies配置为空")
                return False
            
            # 检查是否已有账号使用了这些cookies
            existing_accounts = await self.api.pool.get_all()
            cookies_account_exists = False
            
            for account in existing_accounts:
                # 检查账号是否有相同的cookies（简单比较）
                if hasattr(account, 'cookies') and account.cookies:
                    if cookies_str in str(account.cookies):
                        cookies_account_exists = True
                        logging.info(f"找到已有的Cookies账号: {account.username}")
                        break
            
            # 如果没有找到cookies账号，创建一个新的
            if not cookies_account_exists:
                # 创建一个唯一的用户名用于cookies账号
                cookies_username = f"cookies_user_{int(time.time())}"
                
                try:
                    # 使用twscrape的正确方式：在add_account时直接提供cookies
                    await self.api.pool.add_account(
                        username=cookies_username,
                        password="dummy_password",  # 使用cookies时密码不重要
                        email="dummy@example.com",  # 使用cookies时邮箱不重要
                        email_password="dummy_password",  # 使用cookies时邮箱密码不重要
                        cookies=cookies_str  # 关键：直接在这里提供cookies
                    )
                    # 立即刷新输出缓冲区
                    import sys
                    sys.stdout.flush()
                    sys.stderr.flush()
                    logging.info(f"成功添加Cookies账号: {cookies_username}")
                except Exception as e:
                    logging.error(f"添加Cookies账号失败: {e}")
                    return False
            
            self.is_initialized = True
            logging.info("Twitter API初始化成功")
            
            # 确保所有输出都被刷新
            import sys
            sys.stdout.flush()
            sys.stderr.flush()
            
            return True
            
        except Exception as e:
            self.last_error = str(e)
            logging.error(f"Twitter API初始化失败: {e}")
            return False
    
    def _is_cache_valid(self, username: str) -> bool:
        """检查缓存是否有效"""
        # 默认启用缓存
        if username not in self._cache:
            return False
            
        expire_time = self._cache_expire.get(username, 0)
        return time.time() < expire_time
    
    def _get_from_cache(self, username: str) -> Optional[int]:
        """从缓存获取数据"""
        if self._is_cache_valid(username):
            logging.debug(f"从缓存获取 @{username} 的粉丝数: {self._cache[username]}")
            return self._cache[username]
        return None
    
    def _save_to_cache(self, username: str, followers_count: int) -> None:
        """保存到缓存"""
        # 默认启用缓存，24小时过期
        self._cache[username] = followers_count
        expire_hours = 24  # 固定24小时缓存
        self._cache_expire[username] = time.time() + (expire_hours * 3600)
        logging.debug(f"缓存 @{username} 的粉丝数: {followers_count}")
    
    async def _get_user_followers_async(self, username: str) -> Optional[int]:
        """异步获取用户粉丝数"""
        try:
            # 检查缓存
            cached_result = self._get_from_cache(username)
            if cached_result is not None:
                return cached_result
            
            # 初始化API
            if not await self._initialize_api():
                return None
            
            # 获取用户信息
            logging.info(f"正在获取 @{username} 的粉丝数...")
            
            # 使用twscrape获取用户信息
            user_info = await self.api.user_by_login(username)
            
            if user_info and hasattr(user_info, 'followersCount'):
                followers_count = user_info.followersCount
                logging.info(f"@{username} 的粉丝数: {followers_count:,}")
                
                # 保存到缓存
                self._save_to_cache(username, followers_count)
                
                return followers_count
            else:
                logging.warning(f"无法获取 @{username} 的用户信息")
                return None
                
        except Exception as e:
            logging.error(f"获取 @{username} 粉丝数时出错: {e}")
            return None
    
    def get_user_followers(self, username: str) -> Optional[int]:
        """
        获取Twitter用户粉丝数（同步接口）
        Args:
            username: Twitter用户名（不包含@符号）
        Returns:
            int or None: 粉丝数，失败时返回None
        """
        if self._should_skip():
            return None
            
        if not username:
            logging.warning("Twitter用户名为空")
            return None
        
        # 清理用户名（移除@符号）
        clean_username = username.lstrip('@')
        
        try:
            # 运行异步函数
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                # 如果事件循环正在运行，创建新的事件循环
                import threading
                result = None
                exception = None
                
                def run_in_thread():
                    nonlocal result, exception
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        result = new_loop.run_until_complete(self._get_user_followers_async(clean_username))
                        new_loop.close()
                    except Exception as e:
                        exception = e
                
                thread = threading.Thread(target=run_in_thread)
                thread.start()
                thread.join(timeout=self.request_config.get('timeout', 30))
                
                if thread.is_alive():
                    logging.error(f"获取 @{clean_username} 粉丝数超时")
                    return None
                    
                if exception:
                    raise exception
                    
                return result
            else:
                return loop.run_until_complete(self._get_user_followers_async(clean_username))
                
        except Exception as e:
            logging.error(f"获取 @{clean_username} 粉丝数失败: {e}")
            return None
    
    def get_followers_with_retry(self, username: str) -> Optional[int]:
        """
        带重试机制的粉丝数获取
        Args:
            username: Twitter用户名
        Returns:
            int or None: 粉丝数，失败时返回None
        """
        if self._should_skip():
            return None
        
        max_retry = self.request_config.get('max_retry', 3)
        retry_delay = self.request_config.get('retry_delay', 5)
        
        for attempt in range(max_retry):
            try:
                result = self.get_user_followers(username)
                if result is not None:
                    return result
                    
                if attempt < max_retry - 1:
                    logging.info(f"获取 @{username} 粉丝数失败，{retry_delay}秒后重试 ({attempt + 1}/{max_retry})")
                    time.sleep(retry_delay)
                    
            except Exception as e:
                logging.error(f"第 {attempt + 1} 次尝试获取 @{username} 粉丝数失败: {e}")
                if attempt < max_retry - 1:
                    time.sleep(retry_delay)
        
        logging.error(f"经过 {max_retry} 次尝试后，仍无法获取 @{username} 粉丝数")
        return None


class TwitterFollowersHelper:
    """Twitter粉丝数获取助手类"""
    
    _api_instance = None
    
    @staticmethod
    def format_followers_count(followers_count):
        """
        格式化粉丝数为千分位格式
        Args:
            followers_count: 粉丝数（可能是数字、字符串或错误信息）
        Returns:
            str: 格式化后的粉丝数字符串
        """
        if not followers_count:
            return ""
        
        # 如果是错误信息，直接返回
        error_messages = ['获取失败', '获取出错', '配置未成功', 'Request failed', 'Parse error']
        if isinstance(followers_count, str) and any(msg in followers_count for msg in error_messages):
            return followers_count
        
        try:
            # 尝试转换为整数
            if isinstance(followers_count, str):
                # 移除可能的千分位符号和空格
                clean_count = followers_count.replace(',', '').replace(' ', '')
                followers_int = int(clean_count)
            else:
                followers_int = int(followers_count)
            
            # 格式化为千分位
            return f"{followers_int:,}"
        except (ValueError, TypeError):
            # 如果转换失败，返回原始值
            return str(followers_count)
    
    @classmethod
    def get_api_instance(cls) -> TwitterFollowersAPI:
        """获取API实例（单例模式）"""
        if cls._api_instance is None:
            cls._api_instance = TwitterFollowersAPI()
        return cls._api_instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置API实例（用于配置更改后）"""
        cls._api_instance = None
        logging.debug("TwitterFollowersAPI实例已重置")
    
    @classmethod
    def get_followers_count(cls, username: str) -> Optional[int]:
        """
        获取Twitter用户粉丝数
        Args:
            username: Twitter用户名
        Returns:
            int or None: 粉丝数，失败时返回None
        """
        if not username:
            return None
            
        api = cls.get_api_instance()
        return api.get_followers_with_retry(username)
    
    @classmethod
    def extract_username_from_url(cls, twitter_url: str) -> Optional[str]:
        """
        从Twitter URL中提取用户名
        Args:
            twitter_url: Twitter URL
        Returns:
            str or None: 提取的用户名，失败时返回None
        """
        if not twitter_url:
            return None
        
        import re
        # 匹配各种Twitter URL格式
        patterns = [
            r'twitter\.com/([^/?]+)',
            r'x\.com/([^/?]+)',
            r'@(\w+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, twitter_url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # 过滤掉一些不是用户名的路径
                if username.lower() not in ['home', 'search', 'explore', 'notifications', 'messages', 'i', 'intent']:
                    return username
        
        return None
    
    @classmethod
    def get_followers_from_url(cls, twitter_url: str) -> Optional[int]:
        """
        从Twitter URL获取粉丝数
        Args:
            twitter_url: Twitter URL
        Returns:
            int or None: 粉丝数，失败时返回None
        """
        username = cls.extract_username_from_url(twitter_url)
        if username:
            return cls.get_followers_count(username)
        return None 