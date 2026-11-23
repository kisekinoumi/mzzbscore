# src/extractors/myanimelist.py
# MyAnimeList 数据提取器（正则网页ID召回 + API详情主路径 + 按错误码受控网页兜底 + 高召回结构化排序 + idMal直连校验）

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.data_process.matcher import score_candidate_info, select_best_candidate
from src.parsers.link_parser import LinkParser
from src.parsers.myanimelist_parser import MyAnimeListDataSetter, MyAnimeListParser
from utils.core.global_variables import get_allowed_years
from utils.core.myanimelist_config import get_myanimelist_api_config
from utils.date.date_processors import MyAnimeListDateProcessor
from utils.network.headers import RequestHeaders
from utils.network.network import fetch_data_with_retry
from utils.parsers.text_processor import build_query_variants

from .base_extractor import BaseExtractor, ExtractorErrorHandler

_WEB_ANIME_HREF_RE = re.compile(r'(?:https?://myanimelist\.net)?(/anime/(\d+)(?:/[^"\'\s<>?#]*)?)')
_WEB_FALLBACK_ELIGIBLE_REASONS = frozenset({"not_configured", "auth_failure", "parse_error"})


class MyAnimeListExtractor(BaseExtractor):
    """MyAnimeList数据提取器"""

    API_BASE = "https://api.myanimelist.net/v2"
    WEB_BASE = "https://myanimelist.net"
    DETAIL_FIELDS = "id,title,alternative_titles,start_date,mean,num_scoring_users,num_episodes"

    def __init__(self):
        super().__init__("MyAnimeList", score_key="mal")
        self.parser = MyAnimeListParser()

    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从MyAnimeList URL中提取已验证URL"""
        return LinkParser.extract_myanimelist_url(url)

    def extract_by_identifier(self, anime, identifier: str) -> bool:
        """通过URL或anime_id提取数据：官方API优先，仅在未配置/鉴权或解析异常时回退网页HTML（404/限流/超时不盲目回退）"""
        web_url = self._build_web_url(identifier)
        anime_id = self._extract_anime_id(identifier)

        if anime_id:
            api_data, err_reason = self._fetch_anime_details_with_reason(anime_id)
            if api_data:
                if web_url:
                    api_data["_mal_url"] = web_url
                return self._set_api_data(anime, api_data)

            if err_reason not in _WEB_FALLBACK_ELIGIBLE_REASONS:
                logging.warning(
                    f"MyAnimeList条目 {anime_id} API请求失败 ({err_reason})，跳过网页回退以避免无效请求或WAF封禁"
                )
                return ExtractorErrorHandler.handle_request_error(
                    anime,
                    self.score_key,
                    "No results found" if err_reason == "not_found" else "Request failed",
                )

            logging.warning(
                f"MyAnimeList API不可用 ({err_reason})，回退到网页详情HTML解析: {web_url}"
            )

        if web_url and self._extract_by_web_url(anime, web_url):
            return True

        return ExtractorErrorHandler.handle_request_error(anime, self.score_key, "Request failed")

    def extract_by_id_mal_verified(self, anime, mal_id_str: str) -> bool:
        """
        使用 AniList 提供的 idMal 直连 MAL 详情接口，并通过年份与窄黑名单无冲突校验后写入。
        """
        anime_id = self._extract_anime_id(mal_id_str)
        if not anime_id:
            return False

        api_data, err_reason = self._fetch_anime_details_with_reason(anime_id)
        candidate_info = None
        if api_data:
            candidate_info = self._build_candidate_info(api_data)
        elif err_reason in _WEB_FALLBACK_ELIGIBLE_REASONS:
            candidate_info = self._build_html_candidate_info(f"{self.WEB_BASE}/anime/{anime_id}")

        if not candidate_info:
            return False

        allowed_years = get_allowed_years()
        cand_year = str(candidate_info.get("year") or "")
        if allowed_years and cand_year and cand_year not in allowed_years:
            logging.info(
                f"跳过AniList关联idMal={anime_id}：MAL放送年份 {cand_year} 不在允许范围 {allowed_years}"
            )
            return False

        scored = score_candidate_info(
            candidate_info,
            anime=anime,
            query=anime.original_name,
            platform_key="mal",
        )
        if scored.hard_blocked:
            logging.info(
                f"跳过AniList关联idMal={anime_id}：存在明确冲突 [{scored.block_reason}]"
            )
            return False

        logging.info(f"通过 AniList idMal={anime_id} 直连匹配 MyAnimeList 条目: {candidate_info.get('name')}")
        return self._set_candidate_data(anime, candidate_info)

    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据：网页搜索定位ID优先，官方API搜索兜底（消除冗余重复网页请求）"""
        variants = build_query_variants(processed_name)
        if not variants:
            return ExtractorErrorHandler.handle_no_results_error(anime, self.score_key)

        # 1) 主路径：MAL 网页搜索（召回日文短标题与别名能力更强）
        for idx, query_variant in enumerate(variants):
            if idx > 0:
                logging.info(f"MyAnimeList网页搜索尝试精简变体: {query_variant}")
            if self._extract_by_web_search(anime, query_variant):
                return True

        # 2) 兜底路径：MAL 官方 API 搜索
        logging.info("MyAnimeList网页搜索未命中合规候选，尝试官方API搜索兜底")
        for query_variant in variants[:2]:
            if self._extract_by_api_search(anime, query_variant):
                return True

        return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, self.score_key)

    def _extract_by_web_search(self, anime, query: str) -> bool:
        """网页搜索正则提取候选 ID 列表，详情优先走官方 API，按高召回置信度引擎择优"""
        web_hits = self._search_web_candidates(query, max_hits=6, item_key=anime.original_name)
        if not web_hits:
            return False

        selected_candidate = select_best_candidate(
            candidates=web_hits,
            extract_candidate_info=self._extract_web_id_candidate_info,
            platform_name=self.platform_name,
            platform_key="mal",
            anime=anime,
            query=query,
            max_attempts=6,
            log_failure=False,
            require_fuzzy_relevance=False,
        )
        if not selected_candidate:
            return False

        return self._set_candidate_data(anime, selected_candidate)

    def _extract_by_api_search(self, anime, query: str) -> bool:
        """官方 API 搜索兜底（开启宽泛通道最低相关性门控，防模糊搜索乱配）"""
        if not get_myanimelist_api_config().is_configured:
            return False

        candidates = self._search_api_candidates(query, item_key=anime.original_name) or []
        if not candidates:
            return False

        selected_candidate = select_best_candidate(
            candidates=candidates,
            extract_candidate_info=self._extract_api_candidate_info,
            platform_name=self.platform_name,
            platform_key="mal",
            anime=anime,
            query=query,
            max_attempts=15,
            log_failure=False,
            require_fuzzy_relevance=True,
        )
        if not selected_candidate:
            return False

        return self._set_candidate_data(anime, selected_candidate)

    def _search_web_candidates(
        self,
        keyword: str,
        *,
        max_hits: int = 6,
        item_key: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        从 MAL 网页搜索 HTML 中用正则提取去重后的 /anime/{id} 候选链接，
        不依赖易受页面改版影响的 <table> DOM 层级。
        """
        web_headers = RequestHeaders.get_filmarks_headers()  # 标准日/英 HTML 浏览器头
        response = fetch_data_with_retry(
            f"{self.WEB_BASE}/anime.php",
            params={"q": keyword, "cat": "anime"},
            headers=web_headers,
            site_code="myanimelist_web",
            item_key=item_key or keyword,
        )
        if not response or response.status_code != 200:
            logging.warning("MyAnimeList网页搜索请求失败")
            return []

        html_text = response.text or ""
        results: List[Dict[str, str]] = []
        seen_ids = set()

        for match in _WEB_ANIME_HREF_RE.finditer(html_text):
            rel_path, anime_id = match.group(1), match.group(2)
            if anime_id in seen_ids:
                continue
            seen_ids.add(anime_id)
            full_url = f"{self.WEB_BASE}{rel_path}"
            results.append({"id": anime_id, "url": full_url})
            if len(results) >= max_hits:
                break

        return results

    def _set_candidate_data(self, anime, selected_candidate: Dict[str, Any]) -> bool:
        """按候选数据来源写入Anime对象"""
        candidate_data = selected_candidate.get("data") or {}
        if not candidate_data:
            return False

        if candidate_data.get("_source") == "html":
            return self._set_html_data(
                anime,
                selected_candidate.get("url") or f"{self.WEB_BASE}/anime/{selected_candidate['id']}",
                candidate_data.get("html"),
                candidate_data.get("parsed_date"),
            )

        return self._set_api_data(anime, candidate_data)

    def _extract_by_web_url(self, anime, url: str) -> bool:
        """通过MAL详情页HTML提取数据"""
        response = fetch_data_with_retry(
            url,
            headers=RequestHeaders.get_filmarks_headers(),
            site_code="myanimelist_web",
        )
        if not response or response.status_code != 200:
            logging.error(f"MyAnimeList页面请求失败: {url}")
            return False

        return self._set_html_data(anime, url, response.text)

    def _set_html_data(
        self,
        anime,
        url: str,
        html_content: Optional[str],
        parsed_date: Optional[str] = None,
    ) -> bool:
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

            if not parsed_date and extracted_data.get("aired_date"):
                parsed_date = MyAnimeListDateProcessor.parse(extracted_data["aired_date"])
                if not parsed_date:
                    logging.warning(f"MyAnimeList日期格式不匹配: {extracted_data['aired_date']}")
                    return False

            # 仅当包含完整年月(YYYYMM)时写入 subject_Date；仅有年份时不伪造月份
            subject_yyyymm = parsed_date if (parsed_date and len(parsed_date) >= 6) else None
            MyAnimeListDataSetter.set_extracted_data(anime, url, extracted_data, subject_yyyymm)
            return True

        except Exception as e:
            logging.error(f"MyAnimeList HTML数据提取失败: {e}")
            return False

    def _build_web_url(self, identifier: str) -> Optional[str]:
        if not identifier:
            return None
        identifier = str(identifier).strip()
        if identifier.isdigit():
            return f"{self.WEB_BASE}/anime/{identifier}"
        return LinkParser.extract_myanimelist_url(identifier)

    @staticmethod
    def _extract_anime_id(identifier: str) -> Optional[int]:
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

    @staticmethod
    def _get_headers() -> Optional[Dict[str, str]]:
        config = get_myanimelist_api_config()
        return config.get_headers()

    def _fetch_anime_details_with_reason(
        self,
        anime_id: int,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """获取动画详情并返回失败原因分类，用于精准控制是否回退网页解析"""
        headers = self._get_headers()
        if not headers:
            return None, "not_configured"

        detail_url = f"{self.API_BASE}/anime/{anime_id}"
        response = fetch_data_with_retry(
            detail_url,
            params={"fields": self.DETAIL_FIELDS},
            headers=headers.copy(),
            site_code="myanimelist_api",
            item_key=str(anime_id),
            allow_error_statuses={401, 403, 404, 429},
        )
        if not response:
            return None, "transport_error"

        if response.status_code in (401, 403):
            return None, "auth_failure"
        if response.status_code == 404:
            return None, "not_found"
        if response.status_code == 429:
            return None, "rate_limited"
        if response.status_code != 200:
            return None, "http_error"

        try:
            return response.json(), ""
        except Exception as e:
            logging.error(f"MyAnimeList条目 {anime_id} JSON解析失败: {e}")
            return None, "parse_error"

    def _fetch_anime_details(self, anime_id: int) -> Optional[Dict[str, Any]]:
        data, _ = self._fetch_anime_details_with_reason(anime_id)
        return data

    def _search_api_candidates(
        self,
        processed_name: str,
        item_key: Optional[str] = None,
    ) -> Optional[list]:
        """使用官方API搜索候选条目"""
        headers = self._get_headers()
        if not headers:
            return None

        search_url = f"{self.API_BASE}/anime"
        response = fetch_data_with_retry(
            search_url,
            params={
                "q": processed_name,
                "limit": 15,
                "fields": self.DETAIL_FIELDS,
            },
            headers=headers.copy(),
            site_code="myanimelist_api",
            item_key=item_key or processed_name,
        )
        if not response:
            logging.warning("MyAnimeList API搜索请求失败")
            return None

        try:
            search_result = response.json()
            return search_result.get("data", [])
        except Exception as e:
            logging.error(f"MyAnimeList搜索结果JSON解析失败: {e}")
            return None

    def _extract_web_id_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """根据网页搜索提取到的 {id, url} 拉取候选详情（API优先，特定错误下网页HTML兜底）"""
        if not isinstance(candidate, dict):
            return None
        candidate_url = candidate.get("url") or ""
        anime_id = self._extract_anime_id(candidate.get("id") or candidate_url)
        if not anime_id:
            return None

        api_data, err_reason = self._fetch_anime_details_with_reason(anime_id)
        if api_data:
            if candidate_url:
                api_data["_mal_url"] = candidate_url
            info = self._build_candidate_info(api_data)
            if info:
                return info

        if err_reason in _WEB_FALLBACK_ELIGIBLE_REASONS and candidate_url:
            return self._build_html_candidate_info(candidate_url)

        return None

    def _build_html_candidate_info(self, candidate_href: str) -> Optional[Dict[str, Any]]:
        """从MAL详情页HTML构建候选信息"""
        response = fetch_data_with_retry(
            candidate_href,
            headers=RequestHeaders.get_filmarks_headers(),
            site_code="myanimelist_web",
        )
        if not response or response.status_code != 200:
            return None

        html_content = response.text
        extracted = MyAnimeListParser.extract_all_data(html_content)
        aired_date_str = extracted.get("aired_date")
        if not aired_date_str:
            return None

        parsed_date = MyAnimeListDateProcessor.parse(aired_date_str)
        if not parsed_date:
            return None

        anime_id = LinkParser.extract_myanimelist_id(candidate_href) or candidate_href
        main_title = MyAnimeListParser.extract_title(html_content) or ""
        ja_title = extracted.get("japanese_title") or ""
        en_title = extracted.get("english_name") or ""
        display_name = ja_title or main_title or "未知名称"
        titles = [t for t in (ja_title, main_title, en_title) if t]

        return {
            "name": display_name,
            "titles": titles,
            "year": parsed_date[:4],
            "id": str(anime_id),
            "url": candidate_href,
            "date": parsed_date if len(parsed_date) >= 6 else "",
            "data": {
                "_source": "html",
                "html": html_content,
                "parsed_date": parsed_date,
            },
        }

    def _extract_api_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取API搜索候选条目信息"""
        node = candidate.get("node") if isinstance(candidate, dict) else None
        if not isinstance(node, dict):
            return None

        candidate_id = node.get("id")
        if not candidate_id:
            return None

        api_data = node
        detail_fields = ("alternative_titles", "start_date", "mean", "num_scoring_users")
        if any(field not in api_data for field in detail_fields):
            detail_data = self._fetch_anime_details(int(candidate_id))
            if not detail_data:
                return None
            api_data = detail_data

        return self._build_candidate_info(api_data)

    @classmethod
    def _build_candidate_info(cls, api_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从MAL API详情数据构建可验证候选信息"""
        extracted_data = MyAnimeListParser.extract_all_data(api_data)
        candidate_id = extracted_data.get("id")
        if not candidate_id:
            return None

        raw_aired = extracted_data.get("aired_date")
        parsed_date = MyAnimeListDateProcessor.parse(raw_aired)
        if not parsed_date:
            logging.info(f"MyAnimeList候选条目 {candidate_id} 没有可验证的开播日期")
            return None

        alt_titles = api_data.get("alternative_titles") or {}
        main_title = (api_data.get("title") or "").strip()
        ja_title = (alt_titles.get("ja") or "").strip()
        en_title = (alt_titles.get("en") or "").strip()
        # 主标题(罗马音)、日文标题、英文标题参与相似度计算；不混入杂乱缩写同义词污染季数判断
        titles = [t for t in (ja_title, main_title, en_title) if t]

        eps_raw = api_data.get("num_episodes")
        episodes = int(eps_raw) if isinstance(eps_raw, int) and eps_raw > 0 else None

        iso_date = raw_aired[:10] if (isinstance(raw_aired, str) and len(raw_aired) >= 10 and raw_aired[4] == "-") else None

        return {
            "name": extracted_data.get("japanese_name") or main_title or "未知名称",
            "titles": titles,
            "year": parsed_date[:4],
            "id": str(candidate_id),
            "url": api_data.get("_mal_url") or f"{cls.WEB_BASE}/anime/{candidate_id}",
            "date": parsed_date if len(parsed_date) >= 6 else "",
            "release_date": iso_date,
            "episodes": episodes,
            "data": api_data,
        }

    def _set_api_data(self, anime, api_data: Dict[str, Any]) -> bool:
        """将API数据写入Anime对象"""
        try:
            extracted_data = MyAnimeListParser.extract_all_data(api_data)
            anime_id = extracted_data.get("id")
            if not anime_id:
                return ExtractorErrorHandler.handle_parse_error(
                    anime, self.score_key, "Invalid anime ID"
                )

            raw_aired = extracted_data.get("aired_date")
            parsed_date = MyAnimeListDateProcessor.parse(raw_aired)
            if raw_aired and not parsed_date:
                logging.warning(f"MyAnimeList日期格式不匹配: {raw_aired}")

            subject_yyyymm = parsed_date if (parsed_date and len(parsed_date) >= 6) else None
            if (
                not anime.exact_start_date
                and isinstance(raw_aired, str)
                and len(raw_aired) >= 10
                and raw_aired[4] == "-"
            ):
                anime.exact_start_date = raw_aired[:10]

            eps_raw = api_data.get("num_episodes")
            if anime.episodes is None and isinstance(eps_raw, int) and eps_raw > 0:
                anime.episodes = eps_raw

            url = api_data.get("_mal_url") or f"{self.WEB_BASE}/anime/{anime_id}"
            MyAnimeListDataSetter.set_extracted_data(anime, url, extracted_data, subject_yyyymm)
            return True

        except Exception as e:
            logging.error(f"MyAnimeList数据提取失败: {e}")
            return ExtractorErrorHandler.handle_parse_error(anime, self.score_key, "Parse error")


def extract_myanimelist_data(anime, processed_name):
    """从MyAnimeList提取动画评分（统一入口）"""
    extractor = MyAnimeListExtractor()
    return extractor.extract_data(anime, processed_name)


def extract_myanimelist_data_by_url(anime, candidate_href):
    """通过URL或ID直接从MyAnimeList提取数据"""
    extractor = MyAnimeListExtractor()
    identifier = extractor.extract_identifier_from_url(candidate_href) or candidate_href
    return extractor.extract_by_identifier(anime, identifier)


def extract_myanimelist_data_by_search(anime, processed_name):
    """通过搜索从MyAnimeList提取动画评分"""
    extractor = MyAnimeListExtractor()
    return extractor.extract_by_search(anime, processed_name)
