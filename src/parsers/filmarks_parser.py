"""
Filmarks解析器
"""

import re
import json
from typing import Optional, Dict, Any
from lxml import html
from .base_parser import HtmlParser


class FilmarksParser(HtmlParser):
    """Filmarks页面解析器"""
    
    def __init__(self):
        super().__init__("Filmarks")
    
    def parse(self, content: str) -> Dict[str, Any]:
        """
        解析Filmarks页面内容
        Args:
            content: HTML内容
        Returns:
            dict: 解析结果
        """
        tree = html.fromstring(content)
        
        # 判断是详情页还是搜索页
        if self._is_detail_page(tree):
            return self._parse_detail_page(tree)
        else:
            return self._parse_search_page(tree)
    
    def _is_detail_page(self, tree) -> bool:
        """判断是否为详情页"""
        # 详情页有特定的标题元素
        title_elements = tree.xpath('//h2[@class="p-content-detail__title"]')
        return bool(title_elements)
    
    def _parse_detail_page(self, tree) -> Dict[str, Any]:
        """
        解析详情页
        Args:
            tree: HTML树
        Returns:
            dict: 解析结果
        """
        result = {
            'score': None,
            'name': None,
            'total': None,
            'date': None
        }
        
        # 提取评分
        score_elements = tree.xpath('//div[@class="c2-rating-l__text"]/text()')
        if score_elements:
            result['score'] = score_elements[0].strip()
            self.log_info(f"提取到评分: {result['score']}")
        else:
            self.log_warning("未找到评分")
        
        # 提取名称
        name_elements = tree.xpath('//h2[@class="p-content-detail__title"]/span/text()')
        if name_elements:
            result['name'] = name_elements[0].strip()
            self.log_info(f"提取到名称: {result['name']}")
        else:
            self.log_warning("未找到名称")
        
        # 提取评分人数
        data_mark_elements = tree.xpath('//div[@class="js-btn-mark"]/@data-mark')
        if data_mark_elements:
            try:
                data_mark_json = data_mark_elements[0].replace('&quot;', '"')
                data_mark = json.loads(data_mark_json)
                result['total'] = str(data_mark.get('count', 'No count found'))
                self.log_info(f"提取到评分人数: {result['total']}")
            except (json.JSONDecodeError, KeyError) as e:
                self.log_error(f"解析评分人数失败: {e}")
        else:
            self.log_warning("未找到评分人数")
        
        # 提取开播日期
        date_elements = tree.xpath('//div[@class="p-content-detail__other-info"]//h3[@class="p-content-detail__other-info-title"][contains(text(), "公開日")]/text()')
        if date_elements:
            date_text = date_elements[0].strip()
            result['date'] = self._extract_date_from_text(date_text)
            if result['date']:
                self.log_info(f"提取到开播日期: {result['date']}")
        else:
            self.log_warning("未找到开播日期")
        
        return result
    
    def _parse_search_page(self, tree) -> Dict[str, Any]:
        """
        解析搜索页
        Args:
            tree: HTML树
        Returns:
            dict: 解析结果
        """
        result = {
            'score': None,
            'name': None,
            'total': None,
            'date': None
        }
        
        # 定位第一个搜索结果
        first_result = tree.xpath('//div[contains(@class, "js-cassette")][1]')
        
        if not first_result:
            self.log_warning("未找到搜索结果")
            return result
        
        first_cassette = first_result[0]
        
        # 在第一个搜索结果中查找评分
        score_elements = first_cassette.xpath(
            './/div[@class="c-rating__score"]//text() | '
            './/*[contains(@class, "score")]//text() | '
            './/*[contains(@class, "rating")]//text()'
        )
        
        if score_elements:
            for score_text in score_elements:
                score_text = score_text.strip()
                # 匹配数字格式的评分（如 4.1, 3.5 等）
                score_match = re.search(r'^(\d+\.?\d*)$', score_text)
                if score_match and score_text != '-':
                    result['score'] = score_match.group(1)
                    self.log_info(f"提取到评分: {result['score']}")
                    break
        else:
            self.log_warning("未找到评分")
        
        # 在第一个搜索结果中查找名称
        name_elements = first_cassette.xpath(
            './/h3[@class="p-content-cassette__title"]//text() | '
            './/*[contains(@class, "title") and not(contains(@class, "reviews-title"))]//text()'
        )
        
        if name_elements:
            for name_text in name_elements:
                clean_name = name_text.strip()
                # 过滤掉太短的文本和无意义的文本
                if clean_name and len(clean_name) > 3 and '検索' not in clean_name:
                    result['name'] = clean_name
                    self.log_info(f"提取到名称: {result['name']}")
                    break
        else:
            self.log_warning("未找到名称")
        
        # 获取评分人数
        total_elements = first_cassette.xpath('.//@data-mark')
        if total_elements:
            try:
                data_mark = json.loads(total_elements[0])
                result['total'] = str(data_mark.get('count', 'No count found'))
                self.log_info(f"提取到评分人数: {result['total']}")
            except (json.JSONDecodeError, KeyError) as e:
                self.log_error(f"解析评分人数失败: {e}")
        else:
            self.log_warning("未找到评分人数")
        
        # 在第一个搜索结果中查找日期信息
        date_elements = first_cassette.xpath(
            './/*[contains(text(), "年")]//text() | '
            './/*[contains(@class, "date")]//text() | '
            './/*[contains(@class, "other-info")]//text()'
        )
        
        if date_elements:
            for date_text in date_elements:
                date_str = date_text.strip()
                extracted_date = self._extract_date_from_text(date_str)
                if extracted_date:
                    result['date'] = extracted_date
                    self.log_info(f"提取到开播日期: {result['date']}")
                    break
        else:
            self.log_warning("未找到开播日期")
        
        return result
    
    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """
        从文本中提取日期（YYYYMM格式）
        Args:
            text: 包含日期的文本
        Returns:
            str or None: YYYYMM格式的日期，未找到返回None
        """
        # 匹配 "YYYY年MM月" 格式
        match = re.search(r'(\d{4})年(\d{2})月', text)
        if match:
            year = match.group(1)
            month = match.group(2)
            return year + month
        
        # 匹配其他可能的日期格式
        match = re.search(r'(\d{4})-(\d{2})-\d{2}', text)
        if match:
            year = match.group(1)
            month = match.group(2)
            return year + month
        
        return None


class FilmarksDataSetter:
    """Filmarks数据设置器，负责将解析结果设置到Anime对象"""
    
    @staticmethod
    def set_parsed_data(anime, url: str, parsed_data: Dict[str, Any]):
        """
        将解析的数据设置到Anime对象
        Args:
            anime: Anime对象
            url: Filmarks URL
            parsed_data: 解析结果
        """
        anime.filmarks_url = url
        anime.score_fm = parsed_data.get('score') or 'No score found'
        anime.filmarks_name = parsed_data.get('name') or 'No name found'
        anime.filmarks_total = parsed_data.get('total') or 'No count found'
        
        if parsed_data.get('date'):
            anime.filmarks_subject_Date = parsed_data['date']
        
        # 记录日志
        FilmarksDataSetter._log_extraction_results(anime)
    
    @staticmethod
    def _log_extraction_results(anime):
        """记录提取结果到日志"""
        import logging
        logging.info(f"Filmarks链接: {anime.filmarks_url}")
        logging.info(f"Filmarks名称: {anime.filmarks_name}")
        logging.info(f"Filmarks评分: {anime.score_fm}")
        logging.info(f"Filmarks评分人数: {anime.filmarks_total}")
        if hasattr(anime, 'filmarks_subject_Date') and anime.filmarks_subject_Date:
            logging.info(f"Filmarks开播日期: {anime.filmarks_subject_Date}")
    
    @staticmethod
    def set_error_state(anime, error_message: str):
        """
        设置错误状态
        Args:
            anime: Anime对象
            error_message: 错误信息
        """
        anime.score_fm = error_message
        import logging
        logging.error(f"Filmarks数据提取失败: {error_message}") 