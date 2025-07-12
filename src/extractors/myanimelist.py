# extractors/myanimelist.py
# 存放MyAnimeList数据提取逻辑

import logging
from urllib.parse import quote
from lxml import html
from typing import Optional, Dict, Any

from .base_extractor import BaseExtractor, CandidateValidator, ExtractorErrorHandler, ExtractorLogger
from src.parsers.myanimelist_parser import MyAnimeListParser, MyAnimeListDataSetter
from src.parsers.link_parser import LinkParser
from utils.network.network import fetch_data_with_retry
from utils.date.date_processors import MyAnimeListDateProcessor


class MyAnimeListExtractor(BaseExtractor):
    """MyAnimeList数据提取器"""
    
    def __init__(self):
        super().__init__("MyAnimeList")
        self.parser = MyAnimeListParser()
    
    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从MyAnimeList URL中提取标识符"""
        return LinkParser.extract_myanimelist_url(url)
    
    def extract_by_identifier(self, anime, identifier: str) -> bool:
        """通过URL直接提取数据"""
        return self._extract_by_url(anime, identifier)
    
    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据"""
        # 注意：ALLOWED_YEARS的导入已移至CandidateValidator中动态获取
        
        keyword_encoded = quote(processed_name)
        search_url = f"https://myanimelist.net/anime.php?q={keyword_encoded}&cat=anime"
        search_response = fetch_data_with_retry(search_url)
        
        if not search_response or search_response.status_code != 200:
            logging.warning("MyAnimeList搜索请求失败")
            return ExtractorErrorHandler.handle_request_error(anime, self.platform_key, 'No results found')
        
        mal_tree = html.fromstring(search_response.content)
        candidate_elements = mal_tree.xpath(
            "//table[@border='0' and @cellpadding='0' and @cellspacing='0' and @width='100%']/tr")
        
        if not candidate_elements or len(candidate_elements) <= 1:
            logging.warning("MyAnimeList未找到搜索结果")
            return ExtractorErrorHandler.handle_no_results_error(anime, self.platform_key)
        
        # 使用CandidateValidator验证候选条目
        selected_candidate = CandidateValidator.validate_candidates(
            candidate_elements[1:],  # 跳过标题行
            self._extract_candidate_info,
            self.platform_name
        )
        
        if not selected_candidate:
            return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, self.platform_key)
        
        # 使用选中的候选条目提取数据
        return self._extract_by_url(anime, selected_candidate['id'], selected_candidate['data'])
    
    def _extract_candidate_info(self, candidate) -> Optional[Dict[str, Any]]:
        """提取候选条目信息"""
        try:
            anime_href_element = candidate.xpath(".//div[1]/a[1]")[0]
        except IndexError:
            return None
        
        candidate_href = anime_href_element.get('href')
        if not candidate_href:
            return None
        
        # 请求候选条目的页面
        mal_candidate_response = fetch_data_with_retry(candidate_href)
        if not mal_candidate_response:
            logging.warning(f"MyAnimeList候选条目 {candidate_href} 页面请求失败")
            return None
        
        candidate_html = mal_candidate_response.text
        
        # 使用解析器提取临时数据
        temp_name = MyAnimeListParser.extract_japanese_name(candidate_html)
        aired_date_str = MyAnimeListParser.extract_aired_date(candidate_html)
        
        # 处理日期验证
        if aired_date_str:
            parsed_date = MyAnimeListDateProcessor.parse(aired_date_str)
            if parsed_date:
                candidate_year = parsed_date[:4]  # 从YYYYMM中提取年份
                return {
                    'name': temp_name or '未知名称',
                    'year': candidate_year,
                    'id': candidate_href,
                    'data': {
                        'html': candidate_html,
                        'parsed_date': parsed_date
                    }
                }
        
        return None
    
    def _extract_by_url(self, anime, url: str, additional_data: Optional[Dict] = None) -> bool:
        """
        从URL提取数据的通用方法
        Args:
            anime: Anime对象
            url: 请求URL
            additional_data: 额外数据（如已解析的HTML内容）
        Returns:
            bool: 是否成功提取数据
        """
        # 如果有额外数据，直接使用；否则请求页面
        if additional_data and 'html' in additional_data:
            html_content = additional_data['html']
            parsed_date = additional_data.get('parsed_date')
        else:
            response = fetch_data_with_retry(url)
            if not response:
                logging.error(f"MyAnimeList页面请求失败: {url}")
                return ExtractorErrorHandler.handle_request_error(anime, self.platform_key, "Request failed")
            
            html_content = response.text
            parsed_date = None
        
        try:
            # 使用解析器提取所有数据
            extracted_data = MyAnimeListParser.extract_all_data(html_content)
            
            # 处理日期（如果没有预解析的日期）
            if not parsed_date and extracted_data['aired_date']:
                parsed_date = MyAnimeListDateProcessor.parse(extracted_data['aired_date'])
                if not parsed_date:
                    logging.warning(f"MyAnimeList日期格式不匹配: {extracted_data['aired_date']}")
            
            # 设置结果到anime对象
            MyAnimeListDataSetter.set_extracted_data(anime, url, extracted_data, parsed_date)
            return True
            
        except Exception as e:
            logging.error(f"MyAnimeList数据提取失败: {e}")
            return ExtractorErrorHandler.handle_parse_error(anime, self.platform_key, "Parse error")


# 保持原有的函数接口，委托给新的类
def extract_myanimelist_data(anime, processed_name):
    """
    从MyAnimeList提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = MyAnimeListExtractor()
    return extractor.extract_data(anime, processed_name)


def extract_myanimelist_data_by_url(anime, candidate_href):
    """
    通过URL直接从MyAnimeList提取数据
    Args:
        anime: Anime对象
        candidate_href: MyAnimeList页面URL
    Returns:
        bool: 是否成功提取数据
    """
    extractor = MyAnimeListExtractor()
    return extractor.extract_by_identifier(anime, candidate_href)


def extract_myanimelist_data_by_search(anime, processed_name):
    """
    通过搜索从MyAnimeList页面提取动画评分
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = MyAnimeListExtractor()
    return extractor.extract_by_search(anime, processed_name)