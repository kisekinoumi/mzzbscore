# utils/link_parser.py
# 链接解析工具，用于从平台URL中提取关键信息

import re
import logging
from typing import Optional, Dict, Any
from openpyxl.cell import Cell


class LinkParser:
    """链接解析器，用于处理各平台的URL格式"""
    
    @staticmethod
    def extract_cell_url(cell: Cell) -> Optional[str]:
        """
        从Excel单元格中提取URL（支持超链接和纯文本）
        Args:
            cell: Excel单元格对象
        Returns:
            str or None: 提取到的URL，如果没有则返回None
        """
        if not cell or not cell.value:
            return None
            
        # 检查是否有超链接
        if hasattr(cell, 'hyperlink') and cell.hyperlink:
            url = cell.hyperlink.target
            if url and isinstance(url, str):
                return url.strip()
        
        # 检查单元格值是否为URL格式的文本
        cell_value = str(cell.value).strip()
        if cell_value and (cell_value.startswith('http://') or cell_value.startswith('https://')):
            return cell_value
            
        return None
    
    @staticmethod
    def extract_bangumi_id(url: str) -> Optional[str]:
        """
        从Bangumi URL中提取subject ID
        Args:
            url: Bangumi URL (如: https://bangumi.tv/subject/509297)
        Returns:
            str or None: subject ID，如果提取失败返回None
        """
        if not url:
            return None
            
        # 匹配模式: https://bangumi.tv/subject/数字 或 https://bgm.tv/subject/数字
        pattern = r'https?://(?:bangumi|bgm)\.tv/subject/(\d+)'
        match = re.search(pattern, url)
        
        if match:
            subject_id = match.group(1)
            logging.info(f"从Bangumi URL提取到subject_id: {subject_id}")
            return subject_id
        else:
            logging.warning(f"无法从Bangumi URL提取subject_id: {url}")
            return None
    
    @staticmethod
    def extract_anilist_id(url: str) -> Optional[str]:
        """
        从AniList URL中提取anime ID
        Args:
            url: AniList URL (如: https://anilist.co/anime/180516 或 https://anilist.co/anime/124223/Season-2/)
        Returns:
            str or None: anime ID，如果提取失败返回None
        """
        if not url:
            return None
            
        # 匹配模式: https://anilist.co/anime/数字
        pattern = r'https?://anilist\.co/anime/(\d+)'
        match = re.search(pattern, url)
        
        if match:
            anime_id = match.group(1)
            logging.info(f"从AniList URL提取到anime_id: {anime_id}")
            return anime_id
        else:
            logging.warning(f"无法从AniList URL提取anime_id: {url}")
            return None
    
    @staticmethod
    def extract_myanimelist_url(url: str) -> Optional[str]:
        """
        验证并返回MyAnimeList URL
        Args:
            url: MyAnimeList URL (如: https://myanimelist.net/anime/58492/Mono)
        Returns:
            str or None: 验证后的URL，如果格式不正确返回None
        """
        if not url:
            return None
            
        # 验证URL格式
        if re.match(r'https?://myanimelist\.net/anime/\d+', url):
            logging.info(f"MyAnimeList URL验证通过: {url}")
            return url
        else:
            logging.warning(f"MyAnimeList URL格式不正确: {url}")
            return None
    
    @staticmethod
    def extract_filmarks_info(url: str) -> Optional[Dict[str, str]]:
        """
        从Filmarks URL中提取相关信息
        Args:
            url: Filmarks URL (如: https://filmarks.com/animes/3964/5997)
        Returns:
            dict or None: 包含提取信息的字典，如果提取失败返回None
        """
        if not url:
            return None
            
        # 匹配模式: https://filmarks.com/animes/数字/数字
        pattern = r'https?://filmarks\.com/animes/(\d+)/(\d+)'
        match = re.search(pattern, url)
        
        if match:
            anime_id = match.group(1)
            series_id = match.group(2)
            logging.info(f"从Filmarks URL提取到anime_id: {anime_id}, series_id: {series_id}")
            return {
                'anime_id': anime_id,
                'series_id': series_id,
                'full_url': url
            }
        else:
            logging.warning(f"无法从Filmarks URL提取信息: {url}")
            return None


class UrlChecker:
    """URL检查器，用于检查Excel行中的链接数据"""
    
    @staticmethod
    def check_row_urls(row, col_helper) -> Dict[str, Optional[str]]:
        """
        检查Excel行中的所有平台URL
        Args:
            row: Excel行对象
            col_helper: Excel列助手
        Returns:
            dict: 包含各平台URL的字典
        """
        from utils.excel_columns import ExcelColumns
        
        url_columns = {
            'bangumi': ExcelColumns.BANGUMI_URL,
            'anilist': ExcelColumns.ANILIST_URL,
            'myanimelist': ExcelColumns.MYANIMELIST_URL,
            'filmarks': ExcelColumns.FILMARKS_URL
        }
        
        extracted_urls = {}
        
        for platform, column_name in url_columns.items():
            col_idx = col_helper.get_col_index(column_name)
            if col_idx is not None:
                cell = row[col_idx]
                url = LinkParser.extract_cell_url(cell)
                extracted_urls[platform] = url
                if url:
                    logging.info(f"找到{platform}链接: {url}")
            else:
                extracted_urls[platform] = None
                logging.warning(f"未找到{platform}的URL列: {column_name}")
        
        return extracted_urls
    
    @staticmethod
    def has_any_url(url_dict: Dict[str, Optional[str]]) -> bool:
        """
        检查是否有任何有效的URL
        Args:
            url_dict: URL字典
        Returns:
            bool: 是否有任何有效URL
        """
        return any(url for url in url_dict.values())
    
    @staticmethod
    def get_available_platforms(url_dict: Dict[str, Optional[str]]) -> list:
        """
        获取有可用URL的平台列表
        Args:
            url_dict: URL字典
        Returns:
            list: 有可用URL的平台名称列表
        """
        return [platform for platform, url in url_dict.items() if url] 