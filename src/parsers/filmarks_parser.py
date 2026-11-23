"""
Filmarks解析器（支持移动端API响应解析 + 网页详情解析 + 网页多候选搜索解析）
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from lxml import html

from utils.date.date_processors import FilmarksDateProcessor

from .base_parser import HtmlParser

_WEB_ANIME_HREF_RE = re.compile(r"/animes/(\d+)/(\d+)")


class FilmarksParser(HtmlParser):
    """Filmarks网页解析器"""

    def __init__(self):
        super().__init__("Filmarks")

    def parse(self, content: str) -> Dict[str, Any]:
        """解析Filmarks页面内容（详情页或搜索页首个结果兼容入口）"""
        tree = html.fromstring(content)
        if self._is_detail_page(tree):
            return self._parse_detail_page(tree)
        candidates = self._parse_search_cassettes(tree, limit=1)
        if candidates:
            return candidates[0]
        return {"score": None, "name": None, "total": None, "date": None}

    def parse_search_candidates(self, content: str, limit: int = 10) -> List[Dict[str, Any]]:
        """解析Filmarks搜索页中的所有候选 js-cassette 列表，提取真实 /animes/{series}/{season} 链接"""
        if not content:
            return []
        try:
            tree = html.fromstring(content)
        except Exception as e:
            self.log_error(f"解析Filmarks搜索HTML失败: {e}")
            return []
        return self._parse_search_cassettes(tree, limit=limit)

    @staticmethod
    def _is_detail_page(tree) -> bool:
        title_elements = tree.xpath('//h2[@class="p-content-detail__title"]')
        return bool(title_elements)

    def _parse_detail_page(self, tree) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "score": None,
            "name": None,
            "total": None,
            "date": None,
            "year": None,
        }

        score_elements = tree.xpath('//div[@class="c2-rating-l__text"]/text()')
        if score_elements:
            score_text = score_elements[0].strip()
            if score_text and score_text != "-":
                result["score"] = score_text

        name_elements = tree.xpath('//h2[@class="p-content-detail__title"]/span/text()')
        if not name_elements:
            name_elements = tree.xpath('//h2[@class="p-content-detail__title"]/text()')
        if name_elements:
            result["name"] = name_elements[0].strip()

        data_mark_elements = tree.xpath('//div[contains(@class, "js-btn-mark")]/@data-mark')
        if data_mark_elements:
            try:
                data_mark_json = data_mark_elements[0].replace("&quot;", '"')
                data_mark = json.loads(data_mark_json)
                if "count" in data_mark:
                    result["total"] = str(data_mark["count"])
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                self.log_error(f"解析评分人数失败: {e}")

        date_elements = tree.xpath(
            '//div[contains(@class, "p-content-detail__other-info")]'
            '//*[contains(text(), "公開日")]/..//text() | '
            '//div[contains(@class, "p-content-detail__other-info")]'
            '//h3[contains(@class, "p-content-detail__other-info-title")][contains(text(), "公開日")]/text()'
        )
        for raw_text in date_elements:
            parsed = self._extract_date_from_text(raw_text.strip())
            if parsed:
                result["date"] = parsed
                result["year"] = parsed[:4]
                break

        return result

    def _parse_search_cassettes(self, tree, limit: int = 10) -> List[Dict[str, Any]]:
        cassettes = tree.xpath('//div[contains(@class, "js-cassette")]')
        if not cassettes:
            self.log_warning("未找到Filmarks网页搜索结果")
            return []

        candidates: List[Dict[str, Any]] = []
        for cassette in cassettes[:limit]:
            season_id: Optional[str] = None
            series_id: Optional[str] = None
            for href in cassette.xpath(".//a/@href"):
                m = _WEB_ANIME_HREF_RE.search(str(href))
                if m:
                    series_id, season_id = m.group(1), m.group(2)
                    break

            name: Optional[str] = None
            name_elements = cassette.xpath(
                './/h3[@class="p-content-cassette__title"]//text() | '
                './/*[contains(@class, "title") and not(contains(@class, "reviews-title"))]//text()'
            )
            for name_text in name_elements:
                clean_name = name_text.strip()
                if clean_name and "検索" not in clean_name:
                    name = clean_name
                    break

            score: Optional[str] = None
            score_elements = cassette.xpath(
                './/div[@class="c-rating__score"]//text() | '
                './/*[contains(@class, "score")]//text() | '
                './/*[contains(@class, "rating")]//text()'
            )
            for score_text in score_elements:
                s_clean = score_text.strip()
                m_s = re.search(r"^(\d+\.?\d*)$", s_clean)
                if m_s and s_clean != "-":
                    score = m_s.group(1)
                    break

            total: Optional[str] = None
            total_elements = cassette.xpath(".//@data-mark")
            for raw_mark in total_elements:
                try:
                    data_mark = json.loads(str(raw_mark).replace("&quot;", '"'))
                    if isinstance(data_mark, dict) and "count" in data_mark:
                        total = str(data_mark["count"])
                        break
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

            date_yyyymm: Optional[str] = None
            date_elements = cassette.xpath(
                './/*[contains(text(), "年")]//text() | '
                './/*[contains(@class, "date")]//text() | '
                './/*[contains(@class, "other-info")]//text()'
            )
            for date_text in date_elements:
                extracted_date = self._extract_date_from_text(date_text.strip())
                if extracted_date:
                    date_yyyymm = extracted_date
                    break

            candidates.append(
                {
                    "id": season_id,
                    "series_id": series_id,
                    "name": name,
                    "original_name": name,
                    "titles": [name] if name else [],
                    "score": score,
                    "total": total,
                    "date": date_yyyymm,
                    "year": date_yyyymm[:4] if date_yyyymm else None,
                    "data": {},
                }
            )

        return candidates

    @staticmethod
    def _extract_date_from_text(text: str) -> Optional[str]:
        return FilmarksDateProcessor.parse(text)


class FilmarksApiParser:
    """Filmarks API响应解析器"""

    @staticmethod
    def parse_search(data: Dict[str, Any]) -> list:
        if not isinstance(data, dict):
            return []
        seasons = data.get("seasons")
        return seasons if isinstance(seasons, list) else []

    @classmethod
    def parse_detail(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        season = data.get("season")
        if not isinstance(season, dict):
            season = data
        return cls.parse_season(season)

    @staticmethod
    def parse_season(season: Dict[str, Any]) -> Dict[str, Any]:
        """解析单个season对象（兼容 ISO 时间戳与 YYYY-Qn 季度格式）"""
        if not isinstance(season, dict):
            return {}

        season_id = season.get("id")
        series_id = season.get("seriesId") or season.get("series_id")
        release_date_raw = season.get("releaseDate") or season.get("releaseQuarter")

        title = (season.get("title") or "").strip()
        original_title = (season.get("originalTitle") or "").strip()
        titles = [t for t in (title, original_title) if t]

        date_yyyymm = FilmarksDateProcessor.parse(str(release_date_raw)) if release_date_raw else None
        iso_or_quarter: Optional[str] = None
        if isinstance(release_date_raw, str):
            r_str = release_date_raw.strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}", r_str):
                iso_or_quarter = r_str[:10]
            elif re.match(r"^\d{4}-Q[1-4]$", r_str, re.IGNORECASE):
                iso_or_quarter = r_str.upper()

        year_str = FilmarksApiParser._extract_year(season, date_yyyymm, iso_or_quarter)

        return {
            "id": str(season_id) if season_id is not None else None,
            "series_id": str(series_id) if series_id is not None else None,
            "score": season.get("averageScore"),
            "name": title or original_title or None,
            "original_name": original_title,
            "titles": titles,
            "total": season.get("markCount"),
            "date": date_yyyymm,
            "release_date": iso_or_quarter,
            "year": year_str,
            "data": season,
        }

    @staticmethod
    def _extract_year(
        season: Dict[str, Any],
        date_yyyymm: Optional[str],
        iso_or_quarter: Optional[str],
    ) -> Optional[str]:
        """优先从实际开播日期提取年份，缺失时回退到 productionYear（避免年末制作次年1月番年份偏差）"""
        if date_yyyymm and len(date_yyyymm) >= 4:
            return date_yyyymm[:4]
        if iso_or_quarter and len(iso_or_quarter) >= 4:
            return iso_or_quarter[:4]
        production_year = season.get("productionYear")
        if production_year:
            return str(production_year)
        return None


class FilmarksDataSetter:
    """Filmarks数据设置器，负责将解析结果设置到Anime对象"""

    @staticmethod
    def set_parsed_data(anime, url: str, parsed_data: Dict[str, Any]):
        score = parsed_data.get("score")
        total = parsed_data.get("total")

        anime.filmarks_url = url
        anime.score_fm = str(score) if score is not None else "No score found"
        anime.filmarks_name = parsed_data.get("name") or "No name found"
        anime.filmarks_original_name = parsed_data.get("original_name") or ""
        anime.filmarks_total = str(total) if total is not None else "No count found"

        parsed_date = parsed_data.get("date")
        if parsed_date and len(str(parsed_date)) >= 6:
            anime.filmarks_subject_Date = str(parsed_date)[:6]
        release_iso = parsed_data.get("release_date")
        if (
            not anime.exact_start_date
            and isinstance(release_iso, str)
            and len(release_iso) >= 10
            and "-Q" not in release_iso
        ):
            anime.exact_start_date = release_iso[:10]

        FilmarksDataSetter._log_extraction_results(anime)

    @staticmethod
    def _log_extraction_results(anime):
        logging.info(f"Filmarks链接: {anime.filmarks_url}")
        logging.info(f"Filmarks名称: {anime.filmarks_name}")
        logging.info(f"Filmarks评分: {anime.score_fm}")
        logging.info(f"Filmarks评分人数: {anime.filmarks_total}")
        if hasattr(anime, "filmarks_subject_Date") and anime.filmarks_subject_Date:
            logging.info(f"Filmarks开播日期: {anime.filmarks_subject_Date}")

    @staticmethod
    def set_error_state(anime, error_message: str):
        anime.score_fm = error_message
        logging.error(f"Filmarks数据提取失败: {error_message}")
