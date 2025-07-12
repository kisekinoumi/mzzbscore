# biz/extractors/myanimelist_parser.py
# MyAnimeList HTML内容解析器

import re
import logging
from typing import Optional, Dict, Any


class MyAnimeListParser:
    """MyAnimeList页面内容解析器"""
    
    @staticmethod
    def extract_japanese_name(html_content: str) -> Optional[str]:
        """
        提取日文名称
        Args:
            html_content: HTML内容
        Returns:
            str or None: 日文名称，提取失败返回None
        """
        match = re.search(r'<span class="dark_text">Japanese:</span>\s*([^<]+)', html_content)
        return match.group(1).strip() if match else None
    
    @staticmethod
    def extract_aired_date(html_content: str) -> Optional[str]:
        """
        提取Aired日期字符串
        Args:
            html_content: HTML内容
        Returns:
            str or None: Aired日期字符串，提取失败返回None
        """
        match = re.search(r'<span class="dark_text">Aired:</span>\s*(?:<td>)?([^<]+)', html_content)
        return match.group(1).strip() if match else None
    
    @staticmethod
    def extract_score(html_content: str) -> Optional[str]:
        """
        提取评分
        Args:
            html_content: HTML内容
        Returns:
            str or None: 评分，提取失败返回None
        """
        match = re.search(r'<span itemprop="ratingValue" class="score-label score-\d+">([\d.]+)', html_content)
        return match.group(1) if match else None
    
    @staticmethod
    def extract_rating_count(html_content: str) -> Optional[str]:
        """
        提取评分人数
        Args:
            html_content: HTML内容
        Returns:
            str or None: 评分人数，提取失败返回None
        """
        match = re.search(r'<span itemprop="ratingCount" style="display: none">(\d+)', html_content)
        return match.group(1) if match else None
    
    @staticmethod
    def extract_all_data(html_content: str) -> Dict[str, Optional[str]]:
        """
        一次性提取所有数据
        Args:
            html_content: HTML内容
        Returns:
            dict: 包含所有提取数据的字典
        """
        return {
            'japanese_name': MyAnimeListParser.extract_japanese_name(html_content),
            'aired_date': MyAnimeListParser.extract_aired_date(html_content),
            'score': MyAnimeListParser.extract_score(html_content),
            'rating_count': MyAnimeListParser.extract_rating_count(html_content)
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
        # 设置基本信息
        anime.myanimelist_url = url
        anime.myanimelist_name = extracted_data.get('japanese_name') or 'No name found'
        anime.score_mal = extracted_data.get('score') or 'No score found'
        anime.myanimelist_total = extracted_data.get('rating_count') or 'No score found'
        
        # 设置日期
        if parsed_date:
            anime.myanimelist_subject_Date = parsed_date
        
        # 记录日志
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