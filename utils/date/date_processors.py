# utils/date/date_processors.py
# 日期处理工具模块，提供各平台通用的日期处理逻辑

import logging
import re
from typing import Any, Dict, Optional


class DateProcessor:
    """日期处理器基类"""

    @staticmethod
    def parse_date_to_yyyymm(date_str: str, date_format: str) -> Optional[str]:
        """将日期字符串解析为YYYYMM格式"""
        if not date_str:
            return None

        try:
            if date_format == "myanimelist":
                return MyAnimeListDateProcessor.parse(date_str)
            if date_format == "bangumi":
                return BangumiDateProcessor.parse(date_str)
            if date_format == "filmarks":
                return FilmarksDateProcessor.parse(date_str)
            if date_format == "anilist":
                return AniListDateProcessor.parse(date_str)
            logging.warning(f"未知的日期格式类型: {date_format}")
            return None
        except Exception as e:
            logging.error(f"日期解析失败 ({date_format}): {date_str} -> {e}")
            return None


class MyAnimeListDateProcessor:
    """MyAnimeList日期处理器"""

    MONTH_MAP = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }
    SEASON_MAP = {
        "winter": "01",
        "spring": "04",
        "summer": "07",
        "fall": "10",
        "autumn": "10",
    }

    @classmethod
    def parse(cls, aired_str: Optional[str]) -> Optional[str]:
        """
        解析 MyAnimeList 日期格式为 YYYYMM（若仅有年份则返回 YYYY）：
        支持 "2026-10-05"、"2026-10"、"Oct 5, 2026 to ?"、"Oct, 2026"、"Oct 2026"、"Fall 2026"、"2026"
        """
        if not aired_str:
            return None

        text = str(aired_str).strip()
        api_match = re.match(r"^(\d{4})-(\d{2})", text)
        if api_match:
            return api_match.group(1) + api_match.group(2)

        match_full = re.search(r"\b([A-Za-z]{3})\s+\d{1,2},\s+((?:19|20)\d{2})\b", text)
        if match_full:
            month = cls.MONTH_MAP.get(match_full.group(1).title())
            if month:
                return match_full.group(2) + month

        match_month_year = re.search(r"\b([A-Za-z]{3}),?\s+((?:19|20)\d{2})\b", text)
        if match_month_year:
            month = cls.MONTH_MAP.get(match_month_year.group(1).title())
            if month:
                return match_month_year.group(2) + month

        match_season = re.search(
            r"\b(winter|spring|summer|fall|autumn)\s+((?:19|20)\d{2})\b",
            text,
            re.IGNORECASE,
        )
        if match_season:
            month = cls.SEASON_MAP.get(match_season.group(1).lower())
            if month:
                return match_season.group(2) + month

        match_year_only = re.match(r"^((?:19|20)\d{2})(?:\s+to\b.*)?$", text, re.IGNORECASE)
        if match_year_only:
            return match_year_only.group(1)

        return None


class BangumiDateProcessor:
    """Bangumi日期处理器"""

    JP_SEASON_MAP = {"冬": "01", "春": "04", "夏": "07", "秋": "10"}

    @classmethod
    def parse(cls, date_str: Optional[str]) -> Optional[str]:
        """支持 '2026-10-05'、'2026-10'、'2026年10月5日'、'2026年4月'、'2026年秋'、'2026年' 等格式"""
        if not date_str:
            return None
        text = str(date_str).strip()
        m_iso = re.match(r"^(\d{4})-(\d{1,2})", text)
        if m_iso:
            return f"{m_iso.group(1)}{int(m_iso.group(2)):02d}"
        m_jp = re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月", text)
        if m_jp:
            return f"{m_jp.group(1)}{int(m_jp.group(2)):02d}"
        m_season = re.search(r"((?:19|20)\d{2})\s*年\s*([春夏秋冬])", text)
        if m_season:
            return f"{m_season.group(1)}{cls.JP_SEASON_MAP[m_season.group(2)]}"
        m_year = re.search(r"((?:19|20)\d{2})\s*年", text)
        if m_year:
            return m_year.group(1)
        if re.fullmatch(r"(?:19|20)\d{2}", text):
            return text
        return None


class FilmarksDateProcessor:
    """Filmarks日期处理器"""

    JP_SEASON_MAP = {"冬": "01", "春": "04", "夏": "07", "秋": "10"}

    @classmethod
    def parse(cls, date_str: Optional[str]) -> Optional[str]:
        """支持 '2026年04月10日'、'2026年4月'、'2026-04-05'、'2026-Q4'、'2026年秋'、'2026年'"""
        if not date_str:
            return None
        text = str(date_str).strip()
        m_iso = re.match(r"^(\d{4})-(\d{2})", text)
        if m_iso:
            return m_iso.group(1) + m_iso.group(2)
        m_q = re.match(r"^(\d{4})-Q([1-4])$", text, re.IGNORECASE)
        if m_q:
            quarter_start_month = (int(m_q.group(2)) - 1) * 3 + 1
            return f"{m_q.group(1)}{quarter_start_month:02d}"
        m_jp = re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月", text)
        if m_jp:
            return f"{m_jp.group(1)}{int(m_jp.group(2)):02d}"
        m_season = re.search(r"((?:19|20)\d{2})\s*年\s*([春夏秋冬])", text)
        if m_season:
            return f"{m_season.group(1)}{cls.JP_SEASON_MAP[m_season.group(2)]}"
        m_year = re.search(r"((?:19|20)\d{2})\s*年", text)
        if m_year:
            return m_year.group(1)
        if re.fullmatch(r"(?:19|20)\d{2}", text):
            return text
        return None


class AniListDateProcessor:
    """AniList日期处理器"""

    @staticmethod
    def parse(start_date_obj: Dict[str, Any]) -> Optional[str]:
        if not start_date_obj:
            return None
        year = start_date_obj.get("year")
        if not year:
            return None
        month = start_date_obj.get("month")
        if month:
            return f"{year}{int(month):02d}"
        return str(year)
