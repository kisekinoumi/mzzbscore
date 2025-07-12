# utils/twitter_parser.py
# Twitter/X 链接解析工具

import re
import logging
from typing import Optional, Dict, Any


class TwitterParser:
    """Twitter/X 链接解析器，用于处理AniList中的Twitter外部链接"""
    
    # Twitter/X 相关的site标识符 - 更严格的匹配
    TWITTER_SITE_IDENTIFIERS = [
        'Twitter', 'twitter', 'TWITTER',
        'X.com', 'x.com', 'X (Twitter)', 'X(Twitter)',
        'twitter.com', 'www.twitter.com',
        'www.x.com'
    ]
    
    @staticmethod
    def extract_twitter_from_external_links(external_links):
        """
        从AniList的externalLinks中提取Twitter信息
        Args:
            external_links: AniList返回的externalLinks数组
        Returns:
            dict: 包含twitter_url和twitter_username的字典，如果没有找到返回空字典
        """
        if not external_links or not isinstance(external_links, list):
            return {}
        
        for link in external_links:
            if TwitterParser._is_twitter_link(link):
                twitter_url = link.get('url', '')
                if twitter_url:
                    username = TwitterParser.extract_username_from_url(twitter_url)
                    if username:
                        logging.info(f"从AniList找到Twitter账号: @{username} ({twitter_url})")
                        return {
                            'twitter_url': twitter_url,
                            'twitter_username': username
                        }
                    else:
                        logging.warning(f"找到疑似Twitter链接但无法解析用户名: {twitter_url}")
        
        return {}
    
    @staticmethod
    def _is_twitter_link(link):
        """
        判断是否为Twitter链接
        Args:
            link: AniList的externalLink对象
        Returns:
            bool: 是否为Twitter链接
        """
        if not isinstance(link, dict):
            return False
        
        # 获取site字段和URL
        site = link.get('site', '').strip()
        url = link.get('url', '').strip().lower()
        
        # 首先检查URL域名（最可靠的方法）
        if TwitterParser._is_twitter_domain(url):
            logging.debug(f"通过URL域名识别为Twitter链接: {url}")
            return True
        
        # 然后检查site字段（需要精确匹配）
        if TwitterParser._is_twitter_site_identifier(site):
            logging.debug(f"通过site字段识别为Twitter链接: site='{site}', url='{url}'")
            return True
            
        return False
    
    @staticmethod
    def _is_twitter_domain(url):
        """
        检查URL是否为Twitter域名
        Args:
            url: URL字符串（小写）
        Returns:
            bool: 是否为Twitter域名
        """
        if not url:
            return False
            
        # 匹配Twitter域名
        twitter_domain_patterns = [
            r'(?:https?://)?(?:www\.)?twitter\.com/',
            r'(?:https?://)?(?:www\.)?x\.com/',
            r'(?:https?://)?mobile\.twitter\.com/',
            r'(?:https?://)?mobile\.x\.com/'
        ]
        
        for pattern in twitter_domain_patterns:
            if re.match(pattern, url):
                return True
                
        return False
    
    @staticmethod
    def _is_twitter_site_identifier(site):
        """
        检查site字段是否为Twitter标识符（精确匹配）
        Args:
            site: site字段值
        Returns:
            bool: 是否为Twitter标识符
        """
        if not site:
            return False
            
        # 精确匹配或包含匹配（但要避免误判）
        exact_matches = ['Twitter', 'twitter', 'TWITTER', 'X', 'x']
        contains_matches = ['twitter.com', 'x.com', 'X.com', 'X (Twitter)', 'X(Twitter)']
        
        # 精确匹配
        if site in exact_matches:
            return True
            
        # 包含匹配（但避免单字符'X'的误判）
        site_lower = site.lower()
        for match in contains_matches:
            if match.lower() in site_lower:
                return True
                
        return False
    
    @staticmethod
    def extract_username_from_url(twitter_url):
        """
        从Twitter URL中提取用户名
        Args:
            twitter_url: Twitter链接
        Returns:
            str or None: Twitter用户名（不包含@符号），如果解析失败返回None
        """
        if not twitter_url:
            return None
        
        # 标准化URL
        url = twitter_url.strip()
        
        # 首先验证这确实是Twitter域名
        if not TwitterParser._is_twitter_domain(url.lower()):
            logging.warning(f"URL不是Twitter域名，无法提取用户名: {twitter_url}")
            return None
        
        # 支持的Twitter URL格式：
        # https://twitter.com/username
        # https://x.com/username
        # https://www.twitter.com/username
        # https://www.x.com/username
        # twitter.com/username (无协议)
        # x.com/username (无协议)
        
        # 使用正则表达式提取用户名
        patterns = [
            r'(?:https?://)?(?:www\.)?(?:twitter|x)\.com/([a-zA-Z0-9_]+)',
            r'(?:https?://)?(?:www\.)?(?:twitter|x)\.com/@([a-zA-Z0-9_]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                # 验证用户名格式（Twitter用户名规则）
                if TwitterParser._is_valid_twitter_username(username):
                    logging.debug(f"成功从Twitter URL提取用户名: {username}")
                    return username
                else:
                    logging.warning(f"提取的Twitter用户名格式不正确: {username}")
        
        logging.warning(f"无法从Twitter URL中提取用户名: {twitter_url}")
        return None
    
    @staticmethod
    def _is_valid_twitter_username(username):
        """
        验证Twitter用户名格式是否正确
        Args:
            username: 用户名
        Returns:
            bool: 是否为有效的Twitter用户名
        """
        if not username:
            return False
        
        # Twitter用户名规则：
        # - 只能包含字母、数字和下划线
        # - 长度在1-15个字符之间
        # - 不能全为数字
        # - 不能是常见的路径名
        
        if not re.match(r'^[a-zA-Z0-9_]{1,15}$', username):
            return False
        
        # 不能全为数字
        if username.isdigit():
            return False
        
        # 排除常见的非用户名路径
        invalid_usernames = [
            'home', 'search', 'explore', 'notifications', 'messages', 
            'i', 'intent', 'settings', 'help', 'about', 'privacy',
            'terms', 'login', 'signup', 'oauth', 'api', 'dev',
            'title', 'id', 'user', 'users', 'admin', 'www'
        ]
        
        if username.lower() in invalid_usernames:
            return False
        
        return True
    
    @staticmethod
    def format_twitter_info_for_display(username, url):
        """
        格式化Twitter信息用于显示
        Args:
            username: Twitter用户名
            url: Twitter链接
        Returns:
            str: 格式化后的显示文本
        """
        if not username or not url:
            return ""
        
        return f"@{username}"
    
    @staticmethod
    def validate_twitter_data(username, url):
        """
        验证Twitter数据的有效性
        Args:
            username: Twitter用户名
            url: Twitter链接
        Returns:
            bool: 数据是否有效
        """
        if not username or not url:
            return False
        
        # 验证用户名格式
        if not TwitterParser._is_valid_twitter_username(username):
            return False
        
        # 验证URL格式（必须是Twitter域名）
        if not TwitterParser._is_twitter_domain(url.lower()):
            return False
        
        return True 