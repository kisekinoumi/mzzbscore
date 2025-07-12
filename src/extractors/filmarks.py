# extractors/filmarks.py
# 存放Filmarks数据提取逻辑

import logging
from urllib.parse import quote
from typing import Optional, Dict, Any

from .base_extractor import BaseExtractor, CandidateValidator, ExtractorErrorHandler, ExtractorLogger
from src.parsers.filmarks_parser import FilmarksParser, FilmarksDataSetter
from src.parsers.link_parser import LinkParser
from utils.network.network import fetch_data_with_retry


class FilmarksExtractor(BaseExtractor):
    """Filmarks数据提取器"""
    
    def __init__(self):
        super().__init__("Filmarks")
        self.parser = FilmarksParser()
    
    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从Filmarks URL中提取标识符"""
        filmarks_info = LinkParser.extract_filmarks_info(url)
        if filmarks_info:
            return filmarks_info['full_url']
        return None
    
    def extract_by_identifier(self, anime, identifier: str) -> bool:
        """通过URL直接提取数据"""
        return self._extract_by_url(anime, identifier)
    
    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据"""
        keyword_encoded = quote(processed_name)
        search_url = f"https://filmarks.com/search/animes?q={keyword_encoded}"
        return self._extract_by_url(anime, search_url)
    
    def _extract_by_url(self, anime, url: str) -> bool:
        """
        从URL提取数据的通用方法
        Args:
            anime: Anime对象
            url: 请求URL
        Returns:
            bool: 是否成功提取数据
        """
        response = fetch_data_with_retry(url)
        
        if not response or response.status_code != 200:
            logging.error(f"Filmarks页面请求失败: {url}")
            return ExtractorErrorHandler.handle_request_error(anime, self.platform_key, "Request failed")
        
        try:
            # 使用解析器解析页面内容
            parsed_data = self.parser.parse(response.text)
            
            # 使用数据设置器将解析结果设置到Anime对象
            FilmarksDataSetter.set_parsed_data(anime, url, parsed_data)
            
            return True
            
        except Exception as e:
            logging.error(f"Filmarks数据提取失败: {e}")
            return ExtractorErrorHandler.handle_parse_error(anime, self.platform_key, "Parse error")


# 保持原有的函数接口，委托给新的类
def extract_filmarks_data(anime, processed_name):
    """
    从Filmarks提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = FilmarksExtractor()
    return extractor.extract_data(anime, processed_name)


def extract_filmarks_data_by_url(anime, filmarks_url):
    """
    通过URL直接从Filmarks条目页面提取数据
    Args:
        anime: Anime对象
        filmarks_url: Filmarks条目页面URL
    Returns:
        bool: 是否成功提取数据
    """
    extractor = FilmarksExtractor()
    return extractor.extract_by_identifier(anime, filmarks_url)


def extract_filmarks_data_by_search(anime, processed_name):
    """
    通过搜索从Filmarks页面提取动画评分
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = FilmarksExtractor()
    return extractor.extract_by_search(anime, processed_name)