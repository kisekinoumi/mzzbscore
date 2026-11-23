# src/extractors/bangumi.py
# Bangumi 数据提取器（复用搜索响应直出数据 + 搜索词布尔排除清洗 + 非动画类型拦截 + Decimal 精确加权评分）

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, List, Optional

import requests

from src.data_process.matcher import select_best_candidate
from src.parsers.link_parser import LinkParser
from utils.date.date_processors import BangumiDateProcessor
from utils.network.headers import BANGUMI_HEADERS
from utils.network.network import fetch_data_with_retry
from utils.parsers.text_processor import build_query_variants, sanitize_bangumi_keyword

from .base_extractor import BaseExtractor, ExtractorErrorHandler, ExtractorLogger

SUBJECT_TYPE_ANIME = 2
SEARCH_LIMIT = 10


class BangumiExtractor(BaseExtractor):
    """Bangumi数据提取器"""

    def __init__(self):
        super().__init__("Bangumi", score_key="bgm")
        self.api_base = "https://api.bgm.tv/v0"
        self.headers = BANGUMI_HEADERS.copy()

    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从Bangumi URL中提取subject ID"""
        return LinkParser.extract_bangumi_id(url)

    def extract_by_identifier(self, anime, subject_id: str) -> bool:
        """通过subject_id直接从Bangumi API提取数据，并校验条目类型为动画 (type=2)"""
        try:
            subject_id_int = int(subject_id)
        except ValueError:
            return ExtractorErrorHandler.handle_parse_error(anime, "bgm", "Invalid subject ID")

        subject_data = self._fetch_subject_data(subject_id_int)
        if not subject_data:
            return ExtractorErrorHandler.handle_request_error(anime, "bgm")

        subject_type = subject_data.get("type")
        if subject_type is not None and subject_type != SUBJECT_TYPE_ANIME:
            logging.warning(
                f"Bangumi条目 {subject_id_int} 不是动画类型 (type={subject_type})，拒绝绑定以防污染评分"
            )
            return ExtractorErrorHandler.handle_parse_error(anime, "bgm", "Not an anime subject")

        self._set_subject_data(anime, subject_id_int, subject_data)
        ExtractorLogger.log_extraction_result(anime, self.platform_name, "bgm")
        return True

    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索从Bangumi API提取数据（支持多变体零结果回退与高召回打分排序）"""
        variants = build_query_variants(processed_name)
        if not variants:
            return ExtractorErrorHandler.handle_no_results_error(anime, "bgm", "No results found")

        had_any_raw_results = False
        for idx, query_variant in enumerate(variants):
            sanitized_kw = sanitize_bangumi_keyword(query_variant)
            if not sanitized_kw:
                continue
            if idx > 0:
                logging.info(f"Bangumi尝试精简搜索词变体: {sanitized_kw}")

            candidates = self._search_candidates(sanitized_kw, item_key=anime.original_name)
            if not candidates:
                continue
            had_any_raw_results = True

            selected_candidate = select_best_candidate(
                candidates=candidates,
                extract_candidate_info=self._extract_candidate_info,
                platform_name=self.platform_name,
                platform_key="bgm",
                anime=anime,
                query=sanitized_kw,
                max_attempts=SEARCH_LIMIT,
                log_failure=(idx == len(variants) - 1),
            )
            if selected_candidate:
                subject_id = selected_candidate["id"]
                subject_data = selected_candidate["data"]
                # 搜索条目若不含 rating 字段则补拉一次详情
                if "rating" not in subject_data:
                    detail = self._fetch_subject_data(subject_id)
                    if detail:
                        subject_data = detail

                self._set_subject_data(anime, subject_id, subject_data)
                if selected_candidate.get("date") and not anime.bangumi_subject_Date:
                    anime.bangumi_subject_Date = selected_candidate["date"]

                ExtractorLogger.log_extraction_result(anime, self.platform_name, "bgm")
                return True

        if not had_any_raw_results:
            return ExtractorErrorHandler.handle_no_results_error(anime, "bgm", "No results found")
        return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, "bgm")

    def _fetch_subject_data(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """获取条目详情"""
        subject_url = f"{self.api_base}/subjects/{subject_id}"
        response = fetch_data_with_retry(
            url=subject_url,
            headers=self.headers.copy(),
            site_code="bangumi",
            item_key=str(subject_id),
        )
        if not response:
            logging.error(f"Bangumi条目 {subject_id} 请求失败")
            return None

        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            logging.error(f"Bangumi条目 {subject_id} JSON解析失败")
            return None

    def _search_candidates(
        self,
        keyword: str,
        item_key: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """搜索动画候选条目 (type=2)"""
        search_url = f"{self.api_base}/search/subjects"
        search_data = {
            "keyword": keyword,
            "filter": {"type": [SUBJECT_TYPE_ANIME]},
        }

        response = fetch_data_with_retry(
            url=search_url,
            method="POST",
            params={"limit": SEARCH_LIMIT},
            data=search_data,
            headers=self.headers.copy(),
            site_code="bangumi",
            item_key=item_key or keyword,
        )
        if not response:
            return None

        try:
            search_result = response.json()
            return search_result.get("data", [])
        except requests.exceptions.JSONDecodeError:
            logging.error("Bangumi搜索结果JSON解析失败")
            return None

    def _extract_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        提取候选条目信息。
        优先直接消费 /v0/search/subjects 已返回的 date / name / rating / eps，
        仅在搜索项缺失 date 时才补打 /v0/subjects/{id} 读取详情与 infobox，大幅减少多余 HTTP 请求。
        """
        try:
            candidate_id = candidate["id"]
            subject_type = candidate.get("type")
            if subject_type is not None and subject_type != SUBJECT_TYPE_ANIME:
                return None

            subject_data = candidate
            date_info = self._extract_date_info(subject_data)
            if not date_info:
                detail_data = self._fetch_subject_data(candidate_id)
                if not detail_data:
                    return None
                subject_data = detail_data
                date_info = self._extract_date_info(subject_data)
                if not date_info:
                    return None

            jp_name = (subject_data.get("name") or "").strip()
            cn_name = (subject_data.get("name_cn") or "").strip()
            display_name = cn_name or jp_name or "No name found"
            titles = [jp_name] if jp_name else ([cn_name] if cn_name else [])

            eps_raw = subject_data.get("eps")
            episodes = int(eps_raw) if isinstance(eps_raw, int) and eps_raw > 0 else None

            return {
                "name": display_name,
                "titles": titles,
                "title_zh": cn_name,
                "year": date_info["year"],
                "id": candidate_id,
                "date": date_info["date"],
                "release_date": date_info.get("iso_date"),
                "episodes": episodes,
                "data": subject_data,
            }
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _extract_infobox_date_str(infobox: Any) -> Optional[str]:
        """当顶层 date 为空时，从 Bangumi infobox 的 '放送开始' / '上映年度' 提取日期文本"""
        if not isinstance(infobox, list):
            return None
        target_keys = {"放送开始", "上映年度", "发售日", "开始"}
        for item in infobox:
            if not isinstance(item, dict):
                continue
            if item.get("key") in target_keys:
                val = item.get("value")
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    @classmethod
    def _extract_date_info(cls, subject_data: Dict[str, Any]) -> Optional[Dict[str, Optional[str]]]:
        """从条目数据（顶层 date 或 infobox）中提取年份与 YYYYMM"""
        raw_date = subject_data.get("date")
        iso_date: Optional[str] = None
        if isinstance(raw_date, str) and raw_date.strip():
            raw_date = raw_date.strip()
            if len(raw_date) >= 10 and raw_date[4] == "-" and raw_date[7] == "-":
                iso_date = raw_date[:10]
            parsed_yyyymm = BangumiDateProcessor.parse(raw_date)
            if parsed_yyyymm:
                return {
                    "year": parsed_yyyymm[:4],
                    "date": parsed_yyyymm if len(parsed_yyyymm) >= 6 else "",
                    "iso_date": iso_date,
                }

        infobox_date = cls._extract_infobox_date_str(subject_data.get("infobox"))
        parsed_infobox = BangumiDateProcessor.parse(infobox_date)
        if parsed_infobox:
            return {
                "year": parsed_infobox[:4],
                "date": parsed_infobox if len(parsed_infobox) >= 6 else "",
                "iso_date": None,
            }

        return None

    def _set_subject_data(self, anime, subject_id: int, subject_data: Dict[str, Any]):
        """设置条目数据（含日文原名、中文译名、开播日期与精确加权评分）"""
        anime.bangumi_url = f"https://bgm.tv/subject/{subject_id}"
        jp_name = (subject_data.get("name") or "").strip()
        cn_name = (subject_data.get("name_cn") or "").strip()
        anime.bangumi_name = jp_name or cn_name or "No name found"
        if cn_name:
            anime.bangumi_chinese_name = cn_name

        eps_raw = subject_data.get("eps")
        if anime.episodes is None and isinstance(eps_raw, int) and eps_raw > 0:
            anime.episodes = eps_raw

        date_info = self._extract_date_info(subject_data)
        if date_info:
            if date_info.get("date"):
                anime.bangumi_subject_Date = date_info["date"]
            if date_info.get("iso_date") and not anime.exact_start_date:
                anime.exact_start_date = date_info["iso_date"]

        self._set_rating_data(anime, subject_data)

    @staticmethod
    def _set_rating_data(anime, subject_data: Dict[str, Any]):
        """使用 Decimal(ROUND_HALF_UP) 从评分直方图精确计算加权平均分"""
        rating = subject_data.get("rating") or {}
        score_counts = rating.get("count") or {}
        total = rating.get("total") or 0

        if score_counts and total and int(total) > 0:
            try:
                total_int = int(total)
                weighted_sum = sum(
                    int(score) * int(count) for score, count in score_counts.items()
                )
                calculated_score = (Decimal(weighted_sum) / Decimal(total_int)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                anime.score_bgm = f"{calculated_score:.2f}"
                anime.bangumi_total = str(total_int)
                return
            except (TypeError, ValueError, ArithmeticError) as e:
                logging.warning(f"Bangumi评分直方图计算异常: {e}")

        anime.score_bgm = "No score available"
        logging.warning("Bangumi条目无评分信息")


def extract_bangumi_data(anime, processed_name):
    """从Bangumi提取动画评分（统一入口）"""
    extractor = BangumiExtractor()
    return extractor.extract_data(anime, processed_name)
