# biz/extractors/myanimelist_parser.py
# MyAnimeList API response parser

import logging
from typing import Optional, Dict, Any


class MyAnimeListParser:
    """MyAnimeList API响应解析器"""

    @staticmethod
    def extract_japanese_name(api_data: Dict[str, Any]) -> Optional[str]:
        """
        提取日文名称，缺失时回退到主标题
        Args:
            api_data: API返回的anime对象
        Returns:
            str or None: 日文名称，提取失败返回None
        """
        alternative_titles = api_data.get('alternative_titles') or {}
        japanese_name = alternative_titles.get('ja')
        if japanese_name:
            return str(japanese_name).strip()

        title = api_data.get('title')
        return str(title).strip() if title else None

    @staticmethod
    def extract_japanese_title(api_data: Dict[str, Any]) -> Optional[str]:
        """
        提取严格意义上的日文标题
        Args:
            api_data: API返回的anime对象
        Returns:
            str or None: 日文标题，提取失败返回None
        """
        alternative_titles = api_data.get('alternative_titles') or {}
        japanese_name = alternative_titles.get('ja')
        return str(japanese_name).strip() if japanese_name else None

    @staticmethod
    def extract_english_name(api_data: Dict[str, Any]) -> Optional[str]:
        """
        提取英文名称
        Args:
            api_data: API返回的anime对象
        Returns:
            str or None: 英文名称，提取失败返回None
        """
        alternative_titles = api_data.get('alternative_titles') or {}
        english_name = alternative_titles.get('en')
        return str(english_name).strip() if english_name else None

    @staticmethod
    def extract_aired_date(api_data: Dict[str, Any]) -> Optional[str]:
        """
        提取API start_date
        Args:
            api_data: API返回的anime对象
        Returns:
            str or None: start_date字符串，提取失败返回None
        """
        start_date = api_data.get('start_date')
        return str(start_date).strip() if start_date else None

    @staticmethod
    def extract_score(api_data: Dict[str, Any]) -> Optional[str]:
        """
        提取评分
        Args:
            api_data: API返回的anime对象
        Returns:
            str or None: 评分，提取失败返回None
        """
        score = api_data.get('mean')
        if score is None:
            return None

        try:
            return f"{float(score):.2f}"
        except (TypeError, ValueError):
            return str(score)

    @staticmethod
    def extract_rating_count(api_data: Dict[str, Any]) -> Optional[str]:
        """
        提取评分人数
        Args:
            api_data: API返回的anime对象
        Returns:
            str or None: 评分人数，提取失败返回None
        """
        count = api_data.get('num_scoring_users')
        if count is None:
            return None
        return str(count)

    @staticmethod
    def extract_all_data(api_data: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        一次性提取所有数据
        Args:
            api_data: API返回的anime对象
        Returns:
            dict: 包含所有提取数据的字典
        """
        return {
            'id': str(api_data.get('id')) if api_data.get('id') is not None else None,
            'japanese_name': MyAnimeListParser.extract_japanese_name(api_data),
            'japanese_title': MyAnimeListParser.extract_japanese_title(api_data),
            'english_name': MyAnimeListParser.extract_english_name(api_data),
            'aired_date': MyAnimeListParser.extract_aired_date(api_data),
            'score': MyAnimeListParser.extract_score(api_data),
            'rating_count': MyAnimeListParser.extract_rating_count(api_data),
        }


class MyAnimeListDataSetter:
    """MyAnimeList数据设置器，负责将解析结果设置到Anime对象"""

    @staticmethod
    def set_extracted_data(anime, url: str, extracted_data: Dict[str, Optional[str]],
                           parsed_date: Optional[str] = None):
        """
        将提取的数据设置到Anime对象并记录日志
        Args:
            anime: Anime对象
            url: MyAnimeList URL
            extracted_data: 提取的数据字典
            parsed_date: 已解析的日期（YYYYMM格式）
        """
        anime.myanimelist_url = url
        anime.myanimelist_name = extracted_data.get('japanese_name') or 'No name found'
        anime.myanimelist_japanese_name = extracted_data.get('japanese_title') or ''
        anime.myanimelist_english_name = extracted_data.get('english_name') or ''
        anime.score_mal = extracted_data.get('score') or 'No score found'
        anime.myanimelist_total = extracted_data.get('rating_count') or 'No score found'

        if parsed_date:
            anime.myanimelist_subject_Date = parsed_date

        MyAnimeListDataSetter._log_extraction_results(anime)

    @staticmethod
    def _log_extraction_results(anime):
        """记录提取结果到日志"""
        logging.info(f"MyAnimeList链接: {anime.myanimelist_url}")
        logging.info(f"MyAnimeList名称: {anime.myanimelist_name}")
        logging.info(f"MyAnimeList评分: {anime.score_mal}")
        logging.info(f"MyAnimeList评分人数: {anime.myanimelist_total}")
        if hasattr(anime, 'myanimelist_subject_Date') and anime.myanimelist_subject_Date:
            logging.info(f"MyAnimeList开播日期: {anime.myanimelist_subject_Date}")

    @staticmethod
    def set_error_state(anime, error_message: str):
        """
        设置错误状态
        Args:
            anime: Anime对象
            error_message: 错误信息
        """
        anime.score_mal = error_message
        logging.error(f"MyAnimeList数据提取失败: {error_message}")
