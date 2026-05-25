# extractors/myanimelist.py
# 存放MyAnimeList数据提取逻辑

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import quote
from typing import Optional, Dict, Any

from lxml import html

from .base_extractor import BaseExtractor, ExtractorErrorHandler
from src.parsers.myanimelist_parser import MyAnimeListParser, MyAnimeListDataSetter
from src.parsers.link_parser import LinkParser
from utils.core.myanimelist_config import get_myanimelist_api_config
from utils.date.date_processors import MyAnimeListDateProcessor
from utils.network.network import fetch_data_with_retry


class MyAnimeListExtractor(BaseExtractor):
    """MyAnimeList数据提取器"""

    API_BASE = "https://api.myanimelist.net/v2"
    DETAIL_FIELDS = "id,title,alternative_titles,start_date,mean,num_scoring_users"

    def __init__(self):
        super().__init__("MyAnimeList")
        self.parser = MyAnimeListParser()
        self.score_key = "mal"

    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从MyAnimeList URL中提取可用于网页优先提取的URL"""
        return LinkParser.extract_myanimelist_url(url)

    def extract_by_identifier(self, anime, identifier: str) -> bool:
        """通过URL或anime_id提取数据，详情API优先，网页HTML兜底"""
        web_url = self._build_web_url(identifier)
        anime_id = self._extract_anime_id(identifier)
        if anime_id and self._extract_by_api_id(anime, anime_id, web_url):
            return True

        logging.warning("MyAnimeList API详情提取失败，回退到网页详情HTML解析")
        if web_url and self._extract_by_web_url(anime, web_url):
            return True

        return ExtractorErrorHandler.handle_request_error(anime, self.score_key, "Request failed")

    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据，网页搜索优先，API搜索兜底"""
        selected_candidate = self._extract_by_web_search(anime, processed_name)
        if selected_candidate:
            return True

        logging.warning("MyAnimeList网页搜索/解析失败，回退到官方API搜索")
        return self._extract_by_api_search(anime, processed_name)

    def _extract_by_api_id(self, anime, anime_id: int, mal_url: Optional[str] = None) -> bool:
        """通过anime_id从MyAnimeList API提取数据"""
        api_data = self._fetch_anime_details(anime_id)
        if not api_data:
            return False

        if mal_url:
            api_data["_mal_url"] = mal_url

        return self._set_api_data(anime, api_data)

    def _extract_by_api_search(self, anime, processed_name: str) -> bool:
        """通过官方API搜索提取数据"""
        if not get_myanimelist_api_config().is_configured:
            return ExtractorErrorHandler.handle_request_error(anime, self.score_key, "Missing MAL API config")

        candidates = self._search_api_candidates(processed_name) or []
        selected_candidate = self._validate_candidates(
            candidates,
            self._extract_api_candidate_info,
            max_attempts=20,
            log_failure=False,
            expected_name=processed_name,
            require_relevance=True,
        )

        if not selected_candidate:
            logging.warning(
                "MyAnimeList官方API搜索未找到符合年份的候选，"
                "尝试使用网页搜索定位anime ID后再调用官方API"
            )
            web_candidates = self._search_web_candidate_urls(processed_name) or []
            selected_candidate = self._validate_candidates(
                web_candidates,
                self._extract_web_id_candidate_info,
                max_attempts=5,
                log_failure=True,
                expected_name=processed_name,
                require_relevance=False,
            )

        if not selected_candidate:
            return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, self.score_key)

        return self._set_candidate_data(anime, selected_candidate)

    def _extract_by_web_search(self, anime, processed_name: str) -> bool:
        """通过MAL网页搜索定位候选，详情数据API优先、HTML兜底"""
        candidate_elements = self._fetch_web_search_candidate_rows(processed_name)
        if not candidate_elements:
            return False

        selected_candidate = self._validate_candidates(
            candidate_elements,
            self._extract_web_candidate_info,
            max_attempts=5,
            log_failure=False,
        )

        if not selected_candidate:
            logging.warning("MyAnimeList网页搜索未找到符合年份的候选条目")
            return False

        return self._set_candidate_data(anime, selected_candidate)

    def _set_candidate_data(self, anime, selected_candidate: Dict[str, Any]) -> bool:
        """按候选数据来源写入Anime对象"""
        candidate_data = selected_candidate.get('data') or {}
        if not candidate_data:
            return False

        if candidate_data.get('_source') == 'html':
            return self._set_html_data(
                anime,
                selected_candidate['id'],
                candidate_data.get('html'),
                candidate_data.get('parsed_date')
            )

        return self._set_api_data(anime, candidate_data)

    def _extract_by_web_url(self, anime, url: str) -> bool:
        """通过MAL详情页HTML提取数据"""
        response = fetch_data_with_retry(url)
        if not response or response.status_code != 200:
            logging.error(f"MyAnimeList页面请求失败: {url}")
            return False

        return self._set_html_data(anime, url, response.text)

    def _set_html_data(self, anime, url: str, html_content: Optional[str],
                       parsed_date: Optional[str] = None) -> bool:
        """解析HTML并写入Anime对象"""
        if not html_content:
            return False

        try:
            extracted_data = MyAnimeListParser.extract_all_data(html_content)
            has_detail_signal = any(
                extracted_data.get(key) for key in ("aired_date", "score", "rating_count")
            )
            if not has_detail_signal:
                logging.warning("MyAnimeList HTML未提取到有效数据")
                return False

            if not parsed_date and extracted_data.get('aired_date'):
                parsed_date = MyAnimeListDateProcessor.parse(extracted_data['aired_date'])
                if not parsed_date:
                    logging.warning(f"MyAnimeList日期格式不匹配: {extracted_data['aired_date']}")
                    return False

            MyAnimeListDataSetter.set_extracted_data(anime, url, extracted_data, parsed_date)
            return True

        except Exception as e:
            logging.error(f"MyAnimeList HTML数据提取失败: {e}")
            return False

    def _fetch_web_search_candidate_rows(self, processed_name: str) -> Optional[list]:
        """获取MAL网页搜索候选行"""
        keyword_encoded = quote(processed_name)
        search_url = f"https://myanimelist.net/anime.php?q={keyword_encoded}&cat=anime"
        response = fetch_data_with_retry(search_url)

        if not response or response.status_code != 200:
            logging.warning("MyAnimeList网页搜索请求失败")
            return None

        try:
            mal_tree = html.fromstring(response.content)
            candidate_elements = mal_tree.xpath(
                "//table[@border='0' and @cellpadding='0' and @cellspacing='0' and @width='100%']/tr"
            )
        except Exception as e:
            logging.error(f"MyAnimeList网页搜索结果解析失败: {e}")
            return None

        if not candidate_elements or len(candidate_elements) <= 1:
            logging.warning("MyAnimeList网页搜索未找到搜索结果")
            return None

        return candidate_elements[1:]

    def _build_web_url(self, identifier: str) -> Optional[str]:
        """从URL或anime ID构造MAL网页详情URL"""
        if not identifier:
            return None

        identifier = str(identifier).strip()
        if identifier.isdigit():
            return f"https://myanimelist.net/anime/{identifier}"

        return LinkParser.extract_myanimelist_url(identifier)

    def _extract_anime_id(self, identifier: str) -> Optional[int]:
        """从URL或纯ID中提取MAL anime ID"""
        if not identifier:
            return None

        identifier = str(identifier).strip()
        anime_id = identifier if identifier.isdigit() else LinkParser.extract_myanimelist_id(identifier)
        if not anime_id:
            return None

        try:
            return int(anime_id)
        except (TypeError, ValueError):
            return None

    def _get_headers(self) -> Optional[Dict[str, str]]:
        config = get_myanimelist_api_config()
        headers = config.get_headers()
        if not headers:
            logging.error(
                "MyAnimeList API未配置。请设置环境变量MAL_CLIENT_ID，"
                "或运行程序时按提示输入API Client ID。"
            )
        return headers

    def _fetch_anime_details(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """获取动画详情"""
        headers = self._get_headers()
        if not headers:
            return None

        detail_url = f"{self.API_BASE}/anime/{anime_id}"
        response = fetch_data_with_retry(
            detail_url,
            params={"fields": self.DETAIL_FIELDS},
            headers=headers,
        )

        if not response:
            logging.error(f"MyAnimeList条目 {anime_id} 请求失败")
            return None

        try:
            return response.json()
        except Exception as e:
            logging.error(f"MyAnimeList条目 {anime_id} JSON解析失败: {e}")
            return None

    def _search_api_candidates(self, processed_name: str) -> Optional[list]:
        """使用官方API搜索候选条目"""
        headers = self._get_headers()
        if not headers:
            return None

        search_url = f"{self.API_BASE}/anime"
        response = fetch_data_with_retry(
            search_url,
            params={
                "q": processed_name,
                "limit": 20,
                "fields": self.DETAIL_FIELDS,
            },
            headers=headers,
        )

        if not response:
            logging.warning("MyAnimeList搜索请求失败")
            return None

        try:
            search_result = response.json()
            return search_result.get("data", [])
        except Exception as e:
            logging.error(f"MyAnimeList搜索结果JSON解析失败: {e}")
            return None

    def _search_web_candidate_urls(self, processed_name: str) -> Optional[list]:
        """
        使用MAL网页搜索页兜底定位anime ID。

        MAL官方API的搜索端点对部分日文标题召回较差；这里仅从网页搜索结果
        提取条目链接/ID，评分、人数、日期仍统一由官方API详情接口获取。
        """
        candidate_elements = self._fetch_web_search_candidate_rows(processed_name)
        if not candidate_elements:
            return None

        candidates = []
        for candidate in candidate_elements:
            href_values = candidate.xpath(".//div[1]/a[1]/@href")
            if not href_values:
                continue

            candidate_href = href_values[0]
            anime_id = LinkParser.extract_myanimelist_id(candidate_href)
            if anime_id:
                candidates.append({"id": anime_id, "url": candidate_href})

        return candidates

    def _extract_web_candidate_info(self, candidate) -> Optional[Dict[str, Any]]:
        """提取网页搜索候选条目信息，详情数据API优先、HTML兜底"""
        try:
            anime_href_element = candidate.xpath(".//div[1]/a[1]")[0]
        except IndexError:
            return None

        candidate_href = anime_href_element.get('href')
        if not candidate_href:
            return None

        return self._build_candidate_info_from_web_url(candidate_href)

    def _build_candidate_info_from_web_url(self, candidate_href: str) -> Optional[Dict[str, Any]]:
        """从MAL网页候选URL构建候选信息，优先使用API详情"""
        anime_id = self._extract_anime_id(candidate_href)
        if anime_id:
            api_data = self._fetch_anime_details(anime_id)
            if api_data:
                api_data["_mal_url"] = candidate_href
                candidate_info = self._build_candidate_info(api_data)
                if candidate_info:
                    return candidate_info

                logging.warning(f"MyAnimeList API详情缺少可验证数据，回退到网页详情解析: {candidate_href}")

        return self._build_html_candidate_info(candidate_href)

    def _build_html_candidate_info(self, candidate_href: str) -> Optional[Dict[str, Any]]:
        """从MAL详情页HTML构建候选信息"""
        response = fetch_data_with_retry(candidate_href)
        if not response or response.status_code != 200:
            logging.warning(f"MyAnimeList候选条目 {candidate_href} 页面请求失败")
            return None

        html_content = response.text
        temp_name = MyAnimeListParser.extract_japanese_name(html_content) or "未知名称"
        aired_date_str = MyAnimeListParser.extract_aired_date(html_content)

        if not aired_date_str:
            logging.info(f"MyAnimeList候选条目 {candidate_href} 没有可验证的开播日期")
            return None

        parsed_date = MyAnimeListDateProcessor.parse(aired_date_str)
        if not parsed_date:
            logging.info(f"MyAnimeList候选条目 {candidate_href} 日期格式不匹配: {aired_date_str}")
            return None

        return {
            'name': temp_name,
            'year': parsed_date[:4],
            'id': candidate_href,
            'date': parsed_date,
            'data': {
                '_source': 'html',
                'html': html_content,
                'parsed_date': parsed_date,
            },
        }

    def _extract_api_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取API候选条目信息"""
        node = candidate.get("node") if isinstance(candidate, dict) else None
        if not isinstance(node, dict):
            return None

        candidate_id = node.get("id")
        if not candidate_id:
            return None

        api_data = node
        detail_fields = ("alternative_titles", "start_date", "mean", "num_scoring_users")
        if any(field not in api_data for field in detail_fields):
            detail_data = self._fetch_anime_details(candidate_id)
            if not detail_data:
                return None
            api_data = detail_data

        return self._build_candidate_info(api_data)

    def _extract_web_id_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用网页搜索得到的anime ID生成候选信息，API详情优先、HTML兜底"""
        candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
        if not candidate_id:
            return None

        candidate_url = candidate.get("url")
        if candidate_url:
            return self._build_candidate_info_from_web_url(candidate_url)

        try:
            anime_id = int(candidate_id)
        except (TypeError, ValueError):
            return None

        api_data = self._fetch_anime_details(anime_id)
        if not api_data:
            return None

        return self._build_candidate_info(api_data)

    def _build_candidate_info(self, api_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从MAL API详情数据构建可验证候选信息"""
        extracted_data = MyAnimeListParser.extract_all_data(api_data)
        candidate_id = extracted_data.get("id")
        if not candidate_id:
            return None

        parsed_date = MyAnimeListDateProcessor.parse(extracted_data.get("aired_date"))
        if not parsed_date:
            logging.info(f"MyAnimeList候选条目 {candidate_id} 没有可验证的开播日期")
            return None

        candidate_year = parsed_date[:4]
        candidate_name = extracted_data.get("japanese_name") or "未知名称"

        return {
            "name": candidate_name,
            "year": candidate_year,
            "id": candidate_id,
            "date": parsed_date,
            "data": api_data,
        }

    def _validate_candidates(
        self,
        candidates,
        extract_candidate_info,
        max_attempts=5,
        log_failure=True,
        expected_name=None,
        require_relevance=False,
    ):
        """验证候选条目并返回符合年份要求的第一个候选"""
        attempts = 0

        for candidate in candidates:
            attempts += 1
            if attempts > max_attempts:
                break

            try:
                candidate_info = extract_candidate_info(candidate)
                if not candidate_info:
                    continue

                candidate_name = candidate_info.get('name', '未知名称')
                candidate_year = candidate_info.get('year')
                candidate_id = candidate_info.get('id')

                from utils.core.global_variables import get_allowed_years
                allowed_years = get_allowed_years()

                if candidate_year and candidate_year in allowed_years:
                    candidate_data = candidate_info.get("data", {})
                    is_relevant = self._is_relevant_candidate(expected_name, candidate_data)
                    if require_relevance and not is_relevant:
                        logging.info(
                            f"跳过{self.platform_name}候选条目名称为 {candidate_name}，"
                            f"{self.platform_name}候选条目 {candidate_id} 放送年份符合要求但标题相关性不足"
                        )
                        continue

                    logging.info(
                        f"选中{self.platform_name}候选条目名称为 {candidate_name}，"
                        f"选中{self.platform_name}候选条目 {candidate_id}，放送年份: {candidate_year}"
                    )
                    return candidate_info

                logging.info(
                    f"选中{self.platform_name}候选条目名称为 {candidate_name}，"
                    f"{self.platform_name}候选条目的放送年份 {candidate_year} 不符合要求"
                )

            except Exception as e:
                logging.warning(f"{self.platform_name}候选条目 {attempts} 处理失败: {e}")
                continue

        if log_failure:
            logging.error(
                f"尝试{max_attempts}次后，没有找到放送年份符合要求的 {self.platform_name} 候选条目"
            )

        return None

    def _is_relevant_candidate(self, expected_name: Optional[str], api_data: Dict[str, Any]) -> bool:
        """判断MAL API候选标题是否与查询名相关，避免只因年份合法而误选"""
        expected_norm = self._normalize_title_text(expected_name)
        if not expected_norm:
            return True

        for title in self._candidate_title_values(api_data):
            title_norm = self._normalize_title_text(title)
            if not title_norm:
                continue

            if expected_norm == title_norm:
                return True

            if len(expected_norm) >= 4 and expected_norm in title_norm:
                return True

            if len(title_norm) >= 4 and title_norm in expected_norm:
                return True

            similarity = SequenceMatcher(None, expected_norm, title_norm).ratio()
            if similarity >= 0.72:
                return True

        return False

    @staticmethod
    def _candidate_title_values(api_data: Dict[str, Any]) -> list:
        """收集MAL API候选的所有可比对标题"""
        titles = []
        title = api_data.get("title")
        if title:
            titles.append(title)

        alternative_titles = api_data.get("alternative_titles") or {}
        for key in ("ja", "en"):
            value = alternative_titles.get(key)
            if value:
                titles.append(value)

        synonyms = alternative_titles.get("synonyms") or []
        if isinstance(synonyms, list):
            titles.extend(synonyms)

        return titles

    @staticmethod
    def _normalize_title_text(value: Optional[str]) -> str:
        """标准化标题用于候选相关性比对"""
        if not value:
            return ""

        text = unicodedata.normalize("NFKC", str(value)).lower()
        return re.sub(r"[\s\-_~:：;；,，、。.!！?？'\"“”‘’\[\]【】()（）/\\|・･☆★♪…·]", "", text)

    def _set_api_data(self, anime, api_data: Dict[str, Any]) -> bool:
        """将API数据写入Anime对象"""
        try:
            extracted_data = MyAnimeListParser.extract_all_data(api_data)
            anime_id = extracted_data.get("id")
            if not anime_id:
                return ExtractorErrorHandler.handle_parse_error(anime, self.score_key, "Invalid anime ID")

            parsed_date = MyAnimeListDateProcessor.parse(extracted_data.get("aired_date"))
            if extracted_data.get("aired_date") and not parsed_date:
                logging.warning(f"MyAnimeList日期格式不匹配: {extracted_data.get('aired_date')}")

            url = api_data.get("_mal_url") or f"https://myanimelist.net/anime/{anime_id}"
            MyAnimeListDataSetter.set_extracted_data(anime, url, extracted_data, parsed_date)
            return True

        except Exception as e:
            logging.error(f"MyAnimeList数据提取失败: {e}")
            return ExtractorErrorHandler.handle_parse_error(anime, self.score_key, "Parse error")


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
        candidate_href: MyAnimeList页面URL或anime ID
    Returns:
        bool: 是否成功提取数据
    """
    extractor = MyAnimeListExtractor()
    identifier = extractor.extract_identifier_from_url(candidate_href) or candidate_href
    return extractor.extract_by_identifier(anime, identifier)


def extract_myanimelist_data_by_search(anime, processed_name):
    """
    通过搜索从MyAnimeList提取动画评分（网页搜索优先，API搜索兜底）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = MyAnimeListExtractor()
    return extractor.extract_by_search(anime, processed_name)
