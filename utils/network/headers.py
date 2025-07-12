# utils/network/headers.py
# 网络请求Headers统一配置管理

from typing import Dict, Optional


class RequestHeaders:
    """网络请求Headers配置类"""
    
    # 通用User-Agent（模拟常见浏览器）
    DEFAULT_USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
    )
    
    # 基础headers组合
    BASE_HEADERS = {
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    # JSON API专用headers
    JSON_API_HEADERS = {
        **BASE_HEADERS,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    
    # HTML页面爬取专用headers
    HTML_HEADERS = {
        **BASE_HEADERS,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    }
    
    # GraphQL专用headers
    GRAPHQL_HEADERS = {
        **BASE_HEADERS,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    
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
        """获取MyAnimeList页面爬取headers"""
        return cls.HTML_HEADERS.copy()
    
    @classmethod
    def get_filmarks_headers(cls) -> Dict[str, str]:
        """获取Filmarks页面爬取headers"""
        return cls.HTML_HEADERS.copy()
    
    @classmethod
    def get_custom_headers(cls, 
                          accept: Optional[str] = None,
                          content_type: Optional[str] = None, 
                          additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        获取自定义headers
        Args:
            accept: Accept头值
            content_type: Content-Type头值  
            additional_headers: 额外的headers字典
        Returns:
            dict: 组装后的headers
        """
        headers = cls.BASE_HEADERS.copy()
        
        if accept:
            headers['Accept'] = accept
        if content_type:
            headers['Content-Type'] = content_type
        if additional_headers:
            headers.update(additional_headers)
            
        return headers


# 为了向后兼容，提供一些常用的headers常量
BANGUMI_HEADERS = RequestHeaders.get_bangumi_headers()
ANILIST_HEADERS = RequestHeaders.get_anilist_headers()
MYANIMELIST_HEADERS = RequestHeaders.get_myanimelist_headers()
FILMARKS_HEADERS = RequestHeaders.get_filmarks_headers()

# 导出常用的headers
__all__ = [
    'RequestHeaders',
    'BANGUMI_HEADERS',
    'ANILIST_HEADERS', 
    'MYANIMELIST_HEADERS',
    'FILMARKS_HEADERS'
] 