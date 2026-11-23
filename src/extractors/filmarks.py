# src/extractors/filmarks.py
# Filmarks 数据提取器（API主路径 + 多候选网页搜索兜底 + 统一结构化排序 + 修复 score_fm 错误状态字段）

import logging
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

from src.data_process.matcher import select_best_candidate
from src.parsers.filmarks_parser import FilmarksApiParser, FilmarksDataSetter, FilmarksParser
from src.parsers.link_parser import LinkParser
from utils.network.headers import FILMARKS_API_HEADERS, FILMARKS_HEADERS
from utils.network.network import fetch_data_with_retry
from utils.parsers.text_processor import build_query_variants

from .base_extractor import BaseExtractor, ExtractorErrorHandler

FILMARKS_API_BASE_URL = "https://api.filmarks.com"
FILMARKS_WEB_BASE_URL = "https://filmarks.com"
MAX_SEARCH_CANDIDATES = 10


class FilmarksExtractor(BaseExtractor):
    """Filmarks数据提取器"""

    def __init__(self):
        super().__init__("Filmarks", score_key="fm")
        self.parser = FilmarksParser()
        self.api_parser = FilmarksApiParser()

    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从Filmarks URL中提取标识符"""
        filmarks_info = LinkParser.extract_filmarks_info(url)
        if filmarks_info:
            return filmarks_info["full_url"]
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

            logging.warning("Filmarks搜索链接缺少q参数，回退到网页搜索解析")
            return self._extract_by_web_search_url(anime, identifier, anime.original_name)

        season_id = self._extract_season_id(identifier)
        if season_id and self._extract_by_api_id(anime, season_id, fallback_url=identifier):
            return True

        if self._is_filmarks_url(identifier):
            logging.warning("Filmarks API详情提取失败，回退到网页详情解析")
            return self._extract_by_web_detail_url(anime, identifier)

        logging.error(f"无法从Filmarks标识符提取season ID: {identifier}")
        return ExtractorErrorHandler.handle_request_error(anime, self.score_key, "Request failed")

    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据：移动端 API 优先，网页多候选解析兜底"""
        variants = build_query_variants(processed_name)
        if not variants:
            return ExtractorErrorHandler.handle_no_results_error(anime, self.score_key)

        api_had_results = False
        api_reachable = False
        for idx, query_variant in enumerate(variants):
            if idx > 0:
                logging.info(f"Filmarks尝试精简搜索词变体: {query_variant}")

            matched, reachable, had_items = self._extract_by_api_search(anime, query_variant)
            api_reachable = api_reachable or reachable
            api_had_results = api_had_results or had_items
            if matched:
                return True

        # 当 API 请求本身失败（如 403 WAF）或 API 零结果时，回退网页搜索多候选解析
        if not api_reachable or not api_had_results:
            logging.info("Filmarks尝试网页搜索兜底解析")
            for query_variant in variants[:2]:
                if self._extract_by_web_search(anime, query_variant):
                    return True

        if not api_had_results and api_reachable:
            return ExtractorErrorHandler.handle_no_results_error(anime, self.score_key)
        return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, self.score_key)

    def _extract_by_api_id(
        self,
        anime,
        season_id: str,
        fallback_url: Optional[str] = None,
    ) -> bool:
        """通过Filmarks API详情接口提取数据"""
        parsed_data = self._fetch_api_detail_data(season_id)
        if not parsed_data:
            return False

        url = self._build_web_url(parsed_data)
        if url == FILMARKS_WEB_BASE_URL and fallback_url and "/animes/" in str(fallback_url):
            url = str(fallback_url)
        FilmarksDataSetter.set_parsed_data(anime, url, parsed_data)
        return True

    def _extract_by_api_search(self, anime, query: str):
        """
        通过Filmarks API搜索并按高召回置信度引擎择优。
        返回 (matched: bool, api_reachable: bool, had_items: bool)
        """
        search_data = self._fetch_api_json(
            f"{FILMARKS_API_BASE_URL}/v2/anime/seasons",
            params={"q": query},
            item_key=anime.original_name,
        )
        if search_data is None:
            return False, False, False

        candidates = self.api_parser.parse_search(search_data)
        if not candidates:
            return False, True, False

        selected_candidate = select_best_candidate(
            candidates=candidates,
            extract_candidate_info=self._extract_api_candidate_info,
            platform_name=self.platform_name,
            platform_key="fm",
            anime=anime,
            query=query,
            max_attempts=MAX_SEARCH_CANDIDATES,
            log_failure=False,
        )
        if not selected_candidate:
            return False, True, True

        url = self._build_web_url(selected_candidate)
        FilmarksDataSetter.set_parsed_data(anime, url, selected_candidate)
        return True, True, True

    def _extract_api_candidate_info(self, season_raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        info = self.api_parser.parse_season(season_raw)
        if not info or not info.get("id"):
            return None
        return info

    def _fetch_api_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        item_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        response = fetch_data_with_retry(
            url,
            params=params,
            headers=FILMARKS_API_HEADERS.copy(),
            use_cache=True,
            site_code="filmarks_api",
            item_key=item_key,
        )
        if not response or response.status_code != 200:
            logging.warning(f"Filmarks API请求失败: {url}")
            return None

        try:
            return response.json()
        except ValueError as e:
            logging.error(f"Filmarks API JSON解析失败: {e}")
            return None

    def _fetch_api_detail_data(self, season_id: str) -> Optional[Dict[str, Any]]:
        data = self._fetch_api_json(
            f"{FILMARKS_API_BASE_URL}/v2/anime/seasons/{season_id}",
            item_key=str(season_id),
        )
        if not data:
            return None

        parsed_data = self.api_parser.parse_detail(data)
        if not parsed_data:
            logging.error(f"Filmarks API详情数据为空: {season_id}")
            return None

        return parsed_data

    @staticmethod
    def _build_web_url(parsed_data: Dict[str, Any]) -> str:
        season_id = parsed_data.get("id")
        series_id = parsed_data.get("series_id")
        if series_id and season_id:
            return f"{FILMARKS_WEB_BASE_URL}/animes/{series_id}/{season_id}"
        return FILMARKS_WEB_BASE_URL

    @staticmethod
    def _extract_season_id(identifier: str) -> Optional[str]:
        if not identifier:
            return None
        identifier = str(identifier).strip()
        if identifier.isdigit():
            return identifier
        filmarks_info = LinkParser.extract_filmarks_info(identifier)
        if filmarks_info:
            return filmarks_info.get("season_id")
        return None

    @staticmethod
    def _is_filmarks_url(identifier: str) -> bool:
        return bool(identifier and str(identifier).startswith("http"))

    @staticmethod
    def _is_filmarks_search_url(identifier: str) -> bool:
        if not identifier:
            return False
        parsed_url = urlparse(str(identifier))
        return parsed_url.netloc in ("filmarks.com", "www.filmarks.com") and parsed_url.path == "/search/animes"

    @staticmethod
    def _extract_query_from_search_url(url: str) -> Optional[str]:
        query_params = parse_qs(urlparse(str(url)).query)
        queries = query_params.get("q")
        if queries:
            return queries[0].strip()
        return None

    def _extract_by_web_search(self, anime, query: str) -> bool:
        keyword_encoded = quote(query)
        search_url = f"{FILMARKS_WEB_BASE_URL}/search/animes?q={keyword_encoded}"
        return self._extract_by_web_search_url(anime, search_url, query)

    def _extract_by_web_search_url(self, anime, search_url: str, query: str) -> bool:
        """从Filmarks网页搜索结果提取多候选并按结构化规则择优，写入真实条目链接"""
        response = fetch_data_with_retry(
            search_url,
            headers=FILMARKS_HEADERS.copy(),
            site_code="filmarks_web",
            item_key=anime.original_name,
        )
        if not response or response.status_code != 200:
            return False

        candidates = self.parser.parse_search_candidates(response.text, limit=MAX_SEARCH_CANDIDATES)
        if not candidates:
            return False

        selected = select_best_candidate(
            candidates=candidates,
            extract_candidate_info=lambda c: c if c.get("id") or c.get("name") else None,
            platform_name=self.platform_name,
            platform_key="fm",
            anime=anime,
            query=query,
            max_attempts=MAX_SEARCH_CANDIDATES,
            log_failure=False,
        )
        if not selected:
            return False

        url = self._build_web_url(selected)
        if url == FILMARKS_WEB_BASE_URL:
            url = search_url
        FilmarksDataSetter.set_parsed_data(anime, url, selected)
        return True

    def _extract_by_web_detail_url(self, anime, url: str) -> bool:
        """从Filmarks详情页面HTML提取数据"""
        response = fetch_data_with_retry(
            url,
            headers=FILMARKS_HEADERS.copy(),
            site_code="filmarks_web",
        )
        if not response or response.status_code != 200:
            logging.error(f"Filmarks页面请求失败: {url}")
            return ExtractorErrorHandler.handle_request_error(
                anime, self.score_key, "Request failed"
            )

        try:
            parsed_data = self.parser.parse(response.text)
            if parsed_data.get("score") is None and parsed_data.get("total") is None and not parsed_data.get("name"):
                return ExtractorErrorHandler.handle_parse_error(
                    anime, self.score_key, "Parse error"
                )
            FilmarksDataSetter.set_parsed_data(anime, url, parsed_data)
            return True
        except Exception as e:
            logging.error(f"Filmarks数据提取失败: {e}")
            return ExtractorErrorHandler.handle_parse_error(anime, self.score_key, "Parse error")


def extract_filmarks_data(anime, processed_name):
    """从Filmarks提取动画评分（统一入口）"""
    extractor = FilmarksExtractor()
    return extractor.extract_data(anime, processed_name)


def extract_filmarks_data_by_url(anime, filmarks_url):
    """通过URL直接从Filmarks条目页面提取数据"""
    extractor = FilmarksExtractor()
    return extractor.extract_by_identifier(anime, filmarks_url)


def extract_filmarks_data_by_search(anime, processed_name):
    """通过搜索从Filmarks提取动画评分"""
    extractor = FilmarksExtractor()
    return extractor.extract_by_search(anime, processed_name)
