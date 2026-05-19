# extractors/filmarks.py
# 存放Filmarks数据提取逻辑

import logging
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import quote, parse_qs, urlparse
from typing import Optional, Dict, Any

from .base_extractor import BaseExtractor, ExtractorErrorHandler
from src.parsers.filmarks_parser import FilmarksParser, FilmarksApiParser, FilmarksDataSetter
from src.parsers.link_parser import LinkParser
from utils.network.network import fetch_data_with_retry
from utils.network.headers import FILMARKS_API_HEADERS, FILMARKS_HEADERS
from utils.core.global_variables import get_allowed_years, get_desired_year


FILMARKS_API_BASE_URL = "https://api.filmarks.com"
FILMARKS_WEB_BASE_URL = "https://filmarks.com"
MAX_API_SEARCH_CANDIDATES = 10


class FilmarksExtractor(BaseExtractor):
    """Filmarks数据提取器"""
    
    def __init__(self):
        super().__init__("Filmarks")
        self.parser = FilmarksParser()
        self.api_parser = FilmarksApiParser()
    
    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从Filmarks URL中提取标识符"""
        filmarks_info = LinkParser.extract_filmarks_info(url)
        if filmarks_info:
            return filmarks_info['full_url']
        if self._is_filmarks_search_url(url):
            return url
        return None
    
    def extract_by_identifier(self, anime, identifier: str) -> bool:
        """通过URL或season ID直接提取数据"""
        if self._is_filmarks_search_url(identifier):
            query = self._extract_query_from_search_url(identifier)
            if query:
                logging.info(f"从Filmarks搜索链接提取搜索词: {query}")
                return self.extract_by_search(anime, query)

            logging.warning("Filmarks搜索链接缺少q参数，回退到网页解析")
            return self._extract_by_web_url(anime, identifier)

        season_id = self._extract_season_id(identifier)
        if season_id and self._extract_by_api_id(anime, season_id):
            return True

        if self._is_filmarks_url(identifier):
            logging.warning("Filmarks API详情提取失败，回退到网页详情解析")
            return self._extract_by_web_url(anime, identifier)

        logging.error(f"无法从Filmarks标识符提取season ID: {identifier}")
        return ExtractorErrorHandler.handle_request_error(anime, self.platform_key, "Request failed")
    
    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据"""
        if self._extract_by_api_search(anime, processed_name):
            return True

        logging.warning("Filmarks API搜索提取失败，回退到网页搜索解析")
        return self._extract_by_web_search(anime, processed_name)

    def _extract_by_api_id(self, anime, season_id: str) -> bool:
        """通过Filmarks API详情接口提取数据"""
        parsed_data = self._fetch_api_detail_data(season_id)
        if not parsed_data:
            return False

        url = self._build_web_url(parsed_data)
        FilmarksDataSetter.set_parsed_data(anime, url, parsed_data)
        return True

    def _extract_by_api_search(self, anime, processed_name: str) -> bool:
        """通过Filmarks API搜索并提取详情数据"""
        search_data = self._fetch_api_json(
            f"{FILMARKS_API_BASE_URL}/v2/anime/seasons",
            params={'q': processed_name}
        )
        if not search_data:
            return False

        candidates = self.api_parser.parse_search(search_data)
        if not candidates:
            logging.warning("Filmarks API未返回搜索结果")
            return False

        selected_candidate = self._select_api_candidate(candidates, processed_name)
        if not selected_candidate:
            return False

        url = self._build_web_url(selected_candidate)
        FilmarksDataSetter.set_parsed_data(anime, url, selected_candidate)
        return True

    def _fetch_api_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """请求Filmarks API并解析JSON"""
        response = fetch_data_with_retry(
            url,
            params=params,
            headers=FILMARKS_API_HEADERS.copy(),
            use_cache=True
        )
        if not response or response.status_code != 200:
            logging.error(f"Filmarks API请求失败: {url}")
            return None

        try:
            return response.json()
        except ValueError as e:
            logging.error(f"Filmarks API JSON解析失败: {e}")
            return None

    def _fetch_api_detail_data(self, season_id: str) -> Optional[Dict[str, Any]]:
        """获取并解析Filmarks API详情数据"""
        data = self._fetch_api_json(f"{FILMARKS_API_BASE_URL}/v2/anime/seasons/{season_id}")
        if not data:
            return None

        parsed_data = self.api_parser.parse_detail(data)
        if not parsed_data:
            logging.error(f"Filmarks API详情数据为空: {season_id}")
            return None

        return parsed_data

    def _select_api_candidate(self, candidates: list, query: str) -> Optional[Dict[str, Any]]:
        """按年份和标题相关性选择Filmarks API候选条目"""
        allowed_years = get_allowed_years()
        desired_year = get_desired_year()
        best_candidate = None
        best_score = -1
        fallback_candidate = None

        for index, candidate in enumerate(candidates[:MAX_API_SEARCH_CANDIDATES], start=1):
            candidate_info = self.api_parser.parse_season(candidate)
            if not candidate_info or not candidate_info.get('id'):
                continue

            candidate_name = candidate_info.get('name') or '未知名称'
            candidate_year = candidate_info.get('year')
            candidate_id = candidate_info.get('id')

            if allowed_years and candidate_year not in allowed_years:
                logging.info(f"跳过Filmarks候选条目名称为 {candidate_name}，Filmarks候选条目的放送年份 {candidate_year} 不符合要求")
                continue

            relevance_score = self._calculate_title_relevance(query, candidate)
            if relevance_score > 0:
                if self._is_high_confidence_candidate(relevance_score, candidate_year):
                    logging.info(
                        f"选中Filmarks候选条目名称为 {candidate_name}，"
                        f"选中Filmarks候选条目 {candidate_id}，"
                        f"放送年份: {candidate_year}"
                    )
                    return candidate_info

                if desired_year and candidate_year == desired_year:
                    relevance_score += 5
                relevance_score -= index * 0.01

                if relevance_score > best_score:
                    best_score = relevance_score
                    best_candidate = candidate_info
            elif fallback_candidate is None:
                fallback_candidate = candidate_info
                logging.info(f"Filmarks候选条目名称为 {candidate_name}，标题未精确匹配，暂存为候选")

        selected_candidate = best_candidate or fallback_candidate
        if selected_candidate:
            logging.info(
                f"选中Filmarks候选条目名称为 {selected_candidate.get('name')}，"
                f"选中Filmarks候选条目 {selected_candidate.get('id')}，"
                f"放送年份: {selected_candidate.get('year')}"
            )
            return selected_candidate

        logging.error(f"尝试{MAX_API_SEARCH_CANDIDATES}次后，没有找到放送年份符合要求的 Filmarks 候选条目")
        return None

    def _calculate_title_relevance(self, query: str, candidate: Dict[str, Any]) -> float:
        """计算搜索词与候选标题的相关性"""
        normalized_query = self._normalize_title(query)
        if not normalized_query:
            return 1

        best_score = 0
        for title in self._candidate_title_values(candidate):
            normalized_title = self._normalize_title(title)
            if not normalized_title:
                continue

            length_diff = abs(len(normalized_title) - len(normalized_query))
            if normalized_title == normalized_query:
                score = 100
            elif normalized_title.startswith(normalized_query):
                score = max(60, 85 - min(length_diff, 25))
            elif normalized_query in normalized_title:
                score = max(45, 70 - min(length_diff, 25))
            elif normalized_query.startswith(normalized_title):
                score = max(35, 60 - min(length_diff, 25))
            else:
                similarity = SequenceMatcher(None, normalized_query, normalized_title).ratio()
                score = similarity * 100 if similarity >= 0.85 else 0

            best_score = max(best_score, score)

        return best_score

    @staticmethod
    def _is_high_confidence_candidate(relevance_score: float, candidate_year: Optional[str]) -> bool:
        """判断候选是否足够可信，可立即选中"""
        desired_year = get_desired_year()
        if desired_year:
            return candidate_year == desired_year and relevance_score >= 90
        return relevance_score >= 95

    @staticmethod
    def _candidate_title_values(candidate: Dict[str, Any]) -> list:
        """获取候选条目的可比对标题"""
        values = [
            candidate.get('title'),
            candidate.get('originalTitle'),
        ]
        return [value for value in values if value]

    @staticmethod
    def _normalize_title(title: Any) -> str:
        """归一化标题，降低标点和全半角差异带来的影响"""
        if title is None:
            return ""

        normalized = unicodedata.normalize('NFKC', str(title)).lower()
        return ''.join(char for char in normalized if char.isalnum())

    @staticmethod
    def _build_web_url(parsed_data: Dict[str, Any]) -> str:
        """根据API数据构造Filmarks网页URL"""
        season_id = parsed_data.get('id')
        series_id = parsed_data.get('series_id')
        if series_id and season_id:
            return f"{FILMARKS_WEB_BASE_URL}/animes/{series_id}/{season_id}"
        return FILMARKS_WEB_BASE_URL

    def _extract_season_id(self, identifier: str) -> Optional[str]:
        """从URL或纯ID中提取Filmarks season ID"""
        if not identifier:
            return None

        identifier = str(identifier).strip()
        if identifier.isdigit():
            return identifier

        filmarks_info = LinkParser.extract_filmarks_info(identifier)
        if filmarks_info:
            return filmarks_info.get('season_id')
        return None

    @staticmethod
    def _is_filmarks_url(identifier: str) -> bool:
        """判断标识符是否为Filmarks URL"""
        return bool(identifier and str(identifier).startswith("http"))

    @staticmethod
    def _is_filmarks_search_url(identifier: str) -> bool:
        """判断标识符是否为Filmarks搜索URL"""
        if not identifier:
            return False

        parsed_url = urlparse(str(identifier))
        return parsed_url.netloc == "filmarks.com" and parsed_url.path == "/search/animes"

    @staticmethod
    def _extract_query_from_search_url(url: str) -> Optional[str]:
        """从Filmarks搜索URL中提取q参数"""
        query_params = parse_qs(urlparse(str(url)).query)
        queries = query_params.get('q')
        if queries:
            return queries[0].strip()
        return None

    def _extract_by_web_search(self, anime, processed_name: str) -> bool:
        """通过Filmarks网页搜索兜底提取数据"""
        keyword_encoded = quote(processed_name)
        search_url = f"https://filmarks.com/search/animes?q={keyword_encoded}"
        return self._extract_by_web_url(anime, search_url)
    
    def _extract_by_web_url(self, anime, url: str) -> bool:
        """
        从Filmarks网页提取数据的兜底方法
        Args:
            anime: Anime对象
            url: 请求URL
        Returns:
            bool: 是否成功提取数据
        """
        response = fetch_data_with_retry(url, headers=FILMARKS_HEADERS.copy())
        
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
