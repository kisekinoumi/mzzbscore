# src/extractors/anilist.py
# AniList GraphQL 数据提取器（单次合并查询减半请求量 + 提取 idMal / romaji + 变体回退与防 429）

import logging
from typing import Any, Dict, List, Optional

from src.data_process.matcher import select_best_candidate
from src.parsers.link_parser import LinkParser
from src.parsers.twitter_parser import TwitterParser
from utils.network.headers import ANILIST_HEADERS
from utils.network.network import fetch_data_with_retry
from utils.parsers.text_processor import build_query_variants

from .base_extractor import BaseExtractor, ExtractorErrorHandler, ExtractorLogger

_MEDIA_FIELDS = """
  id
  idMal
  siteUrl
  countryOfOrigin
  episodes
  season
  seasonYear
  title {
    native
    romaji
    english
  }
  startDate {
    year
    month
    day
  }
  averageScore
  stats {
    scoreDistribution {
      score
      amount
    }
  }
  externalLinks {
    id
    url
    site
    type
  }
"""

_DETAIL_QUERY = f"""
query ($id: Int) {{
  Media (id: $id, type: ANIME) {{
    {_MEDIA_FIELDS}
  }}
}}
"""

_SEARCH_QUERY = f"""
query ($search: String, $perPage: Int) {{
  Page (page: 1, perPage: $perPage) {{
    media (search: $search, type: ANIME, sort: SEARCH_MATCH) {{
      {_MEDIA_FIELDS}
    }}
  }}
}}
"""


class AniListExtractor(BaseExtractor):
    """AniList数据提取器"""

    def __init__(self):
        super().__init__("AniList", score_key="al")
        self.api_url = "https://graphql.anilist.co"
        self.headers = ANILIST_HEADERS.copy()

    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从AniList URL中提取anime ID"""
        return LinkParser.extract_anilist_id(url)

    def extract_by_identifier(self, anime, anime_id: str) -> bool:
        """通过anime_id单次GraphQL请求直接提取完整数据"""
        try:
            anime_id_int = int(anime_id)
        except ValueError:
            return ExtractorErrorHandler.handle_parse_error(anime, "al", "Invalid anime ID")

        media = self._fetch_media_by_id(anime_id_int)
        if not media:
            return ExtractorErrorHandler.handle_request_error(anime, "al")

        self._apply_media_data(anime, media)
        ExtractorLogger.log_extraction_result(anime, self.platform_name, "al")
        ExtractorLogger.log_twitter_info(anime)
        return True

    def extract_by_search(self, anime, processed_name: str) -> bool:
        """
        通过单次合并GraphQL搜索并提取完整数据（请求量较旧版直接减半）；
        若主搜索词返回空或无合规条目，自动尝试精简变体（如剥离 '（第1クール）'、异体字 '冰->氷'）。
        """
        variants = build_query_variants(processed_name)
        if not variants:
            return ExtractorErrorHandler.handle_no_results_error(anime, "al", "No AniList results")

        had_any_results = False
        for idx, query_variant in enumerate(variants):
            if idx > 0:
                logging.info(f"AniList尝试精简搜索词变体: {query_variant}")

            candidates = self._search_candidates(query_variant, item_key=anime.original_name)
            if candidates is None:
                if idx == len(variants) - 1 and not had_any_results:
                    return ExtractorErrorHandler.handle_request_error(anime, "al")
                continue
            if not candidates:
                continue

            had_any_results = True
            selected_candidate = select_best_candidate(
                candidates=candidates,
                extract_candidate_info=self._extract_candidate_info,
                platform_name=self.platform_name,
                platform_key="al",
                anime=anime,
                query=query_variant,
                max_attempts=10,
                log_failure=(idx == len(variants) - 1),
            )
            if selected_candidate:
                self._apply_media_data(anime, selected_candidate["data"])
                ExtractorLogger.log_extraction_result(anime, self.platform_name, "al")
                ExtractorLogger.log_twitter_info(anime)
                return True

        if not had_any_results:
            return ExtractorErrorHandler.handle_no_results_error(anime, "al", "No AniList results")
        return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, "al")

    def _fetch_media_by_id(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """单次请求拉取指定 ID 的完整 Media 数据"""
        response = fetch_data_with_retry(
            self.api_url,
            method="POST",
            data={"query": _DETAIL_QUERY, "variables": {"id": anime_id}},
            headers=self.headers.copy(),
            site_code="anilist",
            item_key=str(anime_id),
        )
        if not response:
            return None

        try:
            payload = response.json()
            if payload.get("errors"):
                logging.warning(f"AniList GraphQL返回错误: {payload['errors'][0].get('message')}")
                return None
            return (payload.get("data") or {}).get("Media")
        except Exception as e:
            logging.error(f"AniList条目 {anime_id} JSON解析失败: {e}")
            return None

    def _search_candidates(
        self,
        search_keyword: str,
        item_key: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """搜索候选条目（单次请求同时带回详情字段）"""
        response = fetch_data_with_retry(
            self.api_url,
            method="POST",
            data={
                "query": _SEARCH_QUERY,
                "variables": {"search": search_keyword, "perPage": 10},
            },
            headers=self.headers.copy(),
            site_code="anilist",
            item_key=item_key or search_keyword,
        )
        if not response:
            return None

        try:
            payload = response.json()
            if payload.get("errors"):
                logging.warning(f"AniList搜索GraphQL错误: {payload['errors'][0].get('message')}")
                return None
            return ((payload.get("data") or {}).get("Page") or {}).get("media") or []
        except Exception as e:
            logging.error(f"AniList搜索结果JSON解析失败: {e}")
            return None

    _SEASON_TO_MONTH = {
        "WINTER": 1,
        "SPRING": 4,
        "SUMMER": 7,
        "FALL": 10,
    }

    @classmethod
    def _extract_year_and_dates(cls, media: Dict[str, Any]) -> Dict[str, Optional[str]]:
        start_date = media.get("startDate") or {}
        year_val = start_date.get("year") or media.get("seasonYear")
        year_str = str(year_val) if year_val else None
        month_val = start_date.get("month")
        day_val = start_date.get("day")
        season_str = str(media.get("season") or "").upper()

        yyyymm: Optional[str] = None
        iso_date: Optional[str] = None
        if year_str:
            if month_val:
                yyyymm = f"{year_str}{int(month_val):02d}"
                if day_val:
                    iso_date = f"{int(year_str):04d}-{int(month_val):02d}-{int(day_val):02d}"
            elif season_str in cls._SEASON_TO_MONTH:
                season_year = str(media.get("seasonYear") or year_str)
                yyyymm = f"{season_year}{cls._SEASON_TO_MONTH[season_str]:02d}"

        return {"year": year_str, "date": yyyymm, "iso_date": iso_date}

    @classmethod
    def _extract_candidate_info(cls, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取AniList候选条目信息"""
        try:
            candidate_id = candidate["id"]
            title_info = candidate.get("title") or {}
            native = (title_info.get("native") or "").strip()
            romaji = (title_info.get("romaji") or "").strip()
            english = (title_info.get("english") or "").strip()
            display_name = native or romaji or english or "No name found"
            titles = [t for t in (native, romaji, english) if t]

            date_info = cls._extract_year_and_dates(candidate)
            eps_raw = candidate.get("episodes")
            episodes = int(eps_raw) if isinstance(eps_raw, int) and eps_raw > 0 else None

            return {
                "name": display_name,
                "japanese_name": native,
                "romaji_name": romaji,
                "english_name": english,
                "titles": titles,
                "year": date_info["year"],
                "id": candidate_id,
                "date": date_info["date"],
                "release_date": date_info["iso_date"],
                "episodes": episodes,
                "country_of_origin": candidate.get("countryOfOrigin") or "",
                "data": candidate,
            }
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def _apply_media_data(cls, anime, media: Dict[str, Any]) -> None:
        """将AniList Media对象一次性写入Anime实例"""
        anime_id = media["id"]
        title_info = media.get("title") or {}
        native = (title_info.get("native") or "").strip()
        romaji = (title_info.get("romaji") or "").strip()
        english = (title_info.get("english") or "").strip()

        anime.anilist_url = f"https://anilist.co/anime/{anime_id}"
        anime.anilist_name = native or romaji or english or "No name found"
        anime.anilist_japanese_name = native
        anime.anilist_romaji_name = romaji
        anime.anilist_english_name = english

        # 保存官方关联 MAL ID（供跨站校验与兜底直连使用）
        id_mal = media.get("idMal")
        if not isinstance(id_mal, bool) and isinstance(id_mal, int) and id_mal > 0:
            anime.id_mal = str(id_mal)

        eps_raw = media.get("episodes")
        if isinstance(eps_raw, int) and eps_raw > 0:
            anime.episodes = eps_raw

        # 开播日期
        date_info = cls._extract_year_and_dates(media)
        if date_info["date"]:
            anime.anilist_subject_Date = date_info["date"]
        if date_info["iso_date"]:
            anime.exact_start_date = date_info["iso_date"]

        # 评分（注意处理 averageScore 为 None 的情况）
        avg_score = media.get("averageScore")
        anime.score_al = str(avg_score) if avg_score is not None else "No score found"

        # 评分人数（汇总 scoreDistribution[].amount）
        stats = media.get("stats") or {}
        score_distribution = stats.get("scoreDistribution") or []
        if score_distribution:
            total_votes = 0
            for score_data in score_distribution:
                amount = score_data.get("amount")
                if amount:
                    try:
                        total_votes += int(amount)
                    except (TypeError, ValueError):
                        continue
            anime.anilist_total = str(total_votes)
        else:
            anime.anilist_total = "No vote data available"
            logging.warning("无法获取AniList评分分布数据")

        # 提取Twitter外部链接
        external_links = media.get("externalLinks") or []
        if external_links:
            twitter_info = TwitterParser.extract_twitter_from_external_links(external_links)
            if twitter_info:
                anime.twitter_username = twitter_info.get("twitter_username", "")
                anime.twitter_url = twitter_info.get("twitter_url", "")
            else:
                logging.info("AniList条目中未找到Twitter链接")
        else:
            logging.info("AniList条目中没有外部链接信息")


def extract_anilist_data(anime, processed_name):
    """从AniList提取动画评分（统一入口）"""
    extractor = AniListExtractor()
    return extractor.extract_data(anime, processed_name)
