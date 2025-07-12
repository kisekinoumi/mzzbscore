# utils/date_processors.py
# 日期处理工具模块，提供各平台通用的日期处理逻辑

import re
import logging
from typing import Optional, Dict, Any


class DateProcessor:
    """日期处理器基类"""
    
    @staticmethod
    def parse_date_to_yyyymm(date_str: str, date_format: str) -> Optional[str]:
        """
        将日期字符串解析为YYYYMM格式
        Args:
            date_str: 原始日期字符串
            date_format: 日期格式类型
        Returns:
            str or None: YYYYMM格式的日期字符串，解析失败返回None
        """
        if not date_str:
            return None
            
        try:
            if date_format == "myanimelist":
                return MyAnimeListDateProcessor.parse(date_str)
            elif date_format == "bangumi":
                return BangumiDateProcessor.parse(date_str)
            elif date_format == "filmarks":
                return FilmarksDateProcessor.parse(date_str)
            elif date_format == "anilist":
                return AniListDateProcessor.parse(date_str)
            else:
                logging.warning(f"未知的日期格式类型: {date_format}")
                return None
        except Exception as e:
            logging.error(f"日期解析失败 ({date_format}): {date_str} -> {e}")
            return None


class MyAnimeListDateProcessor:
    """MyAnimeList日期处理器"""
    
    # 月份英文缩写到数字的映射
    MONTH_MAP = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
    }
    
    @classmethod
    def parse(cls, aired_str: str) -> Optional[str]:
        """
        解析MyAnimeList的Aired日期格式
        Args:
            aired_str: 如 "Jan 10, 2025 to ?" 或 "Jan 10, 2025"
        Returns:
            str or None: YYYYMM格式，解析失败返回None
        """
        if not aired_str:
            return None
            
        # 用正则提取月份英文缩写和年份
        match = re.search(r'([A-Za-z]{3})\s+\d{1,2},\s+(\d{4})', aired_str)
        if match:
            month_abbr = match.group(1)
            year = match.group(2)
            month = cls.MONTH_MAP.get(month_abbr, "00")
            return year + month
        return None


class BangumiDateProcessor:
    """Bangumi日期处理器"""
    
    @staticmethod
    def parse(date_str: str) -> Optional[str]:
        """
        解析Bangumi的日期格式
        Args:
            date_str: 如 "2025-01-10"
        Returns:
            str or None: YYYYMM格式，解析失败返回None
        """
        if not date_str:
            return None
            
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            year = date_str[:4]
            month = date_str[5:7]
            return year + month
        return None


class FilmarksDateProcessor:
    """Filmarks日期处理器"""
    
    @staticmethod
    def parse(date_str: str) -> Optional[str]:
        """
        解析Filmarks的日期格式
        Args:
            date_str: 如 "公開日：2025年01月10日" 或 "2025年01月"
        Returns:
            str or None: YYYYMM格式，解析失败返回None
        """
        if not date_str:
            return None
            
        # 匹配 "2025年01月" 格式
        match = re.search(r'(\d{4})年(\d{2})月', date_str)
        if match:
            year = match.group(1)
            month = match.group(2)
            return year + month
        return None


class AniListDateProcessor:
    """AniList日期处理器"""
    
    @staticmethod
    def parse(start_date_obj: Dict[str, Any]) -> Optional[str]:
        """
        解析AniList的startDate对象
        Args:
            start_date_obj: 如 {"year": 2025, "month": 1}
        Returns:
            str or None: YYYYMM格式，解析失败返回None
        """
        if not start_date_obj:
            return None
            
        year = start_date_obj.get('year')
        if not year:
            return None
            
        month = start_date_obj.get('month')
        if month:
            return f"{year}{month:02d}"
        else:
            return str(year) 