# biz/extractors/bangumi_refactored.py
# 重构后的Bangumi数据提取逻辑

import re
import logging
import requests
from typing import Optional, Dict, Any
from utils import fetch_data_with_retry, LinkParser
from .base_extractor import BaseExtractor, CandidateValidator, ExtractorErrorHandler, ExtractorLogger


class BangumiExtractor(BaseExtractor):
    """Bangumi数据提取器"""
    
    def __init__(self):
        super().__init__("Bangumi")
        self.api_base = "https://api.bgm.tv/v0"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42'
        }
    
    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从Bangumi URL中提取subject ID"""
        return LinkParser.extract_bangumi_id(url)
    
    def extract_by_identifier(self, anime, subject_id: str) -> bool:
        """通过subject_id直接从Bangumi API提取数据"""
        try:
            subject_id_int = int(subject_id)
        except ValueError:
            return ExtractorErrorHandler.handle_parse_error(anime, "bgm", "Invalid subject ID")
        
        # 获取条目详情
        subject_data = self._fetch_subject_data(subject_id_int)
        if not subject_data:
            return ExtractorErrorHandler.handle_request_error(anime, "bgm")
        
        # 设置数据
        self._set_subject_data(anime, subject_id_int, subject_data)
        
        # 记录日志
        ExtractorLogger.log_extraction_result(anime, self.platform_name, "bgm")
        return True
    
    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索从Bangumi API提取数据"""
        # 搜索候选条目
        candidates = self._search_candidates(processed_name)
        if not candidates:
            return ExtractorErrorHandler.handle_no_results_error(anime, "bgm", "No results found")
        
        # 验证候选条目
        selected_candidate = CandidateValidator.validate_candidates(
            candidates=candidates,
            extract_candidate_info=self._extract_candidate_info,
            platform_name=self.platform_name,
            max_attempts=5
        )
        
        if not selected_candidate:
            return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, "bgm")
        
        # 使用选中的候选条目
        subject_id = selected_candidate['id']
        subject_data = selected_candidate['data']
        
        # 设置数据
        self._set_subject_data(anime, subject_id, subject_data)
        anime.bangumi_subject_Date = selected_candidate['date']
        
        # 记录日志
        ExtractorLogger.log_extraction_result(anime, self.platform_name, "bgm")
        return True
    
    def _fetch_subject_data(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """获取条目详情"""
        subject_url = f"{self.api_base}/subjects/{subject_id}"
        response = fetch_data_with_retry(url=subject_url, headers=self.headers)
        
        if not response:
            logging.error(f"Bangumi条目 {subject_id} 请求失败")
            return None
        
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            logging.error(f"Bangumi条目 {subject_id} JSON解析失败")
            return None
    
    def _search_candidates(self, processed_name: str) -> Optional[list]:
        """搜索候选条目"""
        search_url = f"{self.api_base}/search/subjects"
        search_data = {
            "keyword": processed_name,
            "filter": {"type": [2]}  # 2 表示动画类型
        }
        
        response = fetch_data_with_retry(
            url=search_url,
            method='POST',
            params={"limit": 5},
            data=search_data,
            headers=self.headers
        )
        
        if not response:
            return None
        
        try:
            search_result = response.json()
            # 保存返回数据到文件方便调试（可选）
            with open("outporiginal_name.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            return search_result.get('data', [])
        except requests.exceptions.JSONDecodeError:
            logging.error("Bangumi搜索结果JSON解析失败")
            return None
    
    def _extract_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取候选条目信息"""
        try:
            candidate_id = candidate['id']
            candidate_name = candidate.get('name_cn', 'No name found')
            
            # 获取候选条目的详细信息以获取日期
            subject_data = self._fetch_subject_data(candidate_id)
            if not subject_data:
                return None
            
            # 提取日期信息
            date_info = self._extract_date_info(subject_data)
            if not date_info:
                return None
            
            return {
                'name': candidate_name,
                'year': date_info['year'],
                'id': candidate_id,
                'date': date_info['date'],
                'data': subject_data
            }
            
        except (KeyError, TypeError):
            return None
    
    def _extract_date_info(self, subject_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """从条目数据中提取日期信息"""
        if "date" not in subject_data or not isinstance(subject_data["date"], str):
            return None
        
        date_str = subject_data["date"]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            logging.warning(f"Bangumi日期格式不正确: {date_str}")
            return None
        
        year = date_str[:4]
        month = date_str[5:7]
        date_yyyymm = year + month
        
        return {
            'year': year,
            'date': date_yyyymm
        }
    
    def _set_subject_data(self, anime, subject_id: int, subject_data: Dict[str, Any]):
        """设置条目数据"""
        # 设置基本信息
        anime.bangumi_url = f"https://bgm.tv/subject/{subject_id}"
        anime.bangumi_name = subject_data.get('name', 'No name found')
        
        # 处理开播日期
        date_info = self._extract_date_info(subject_data)
        if date_info:
            anime.bangumi_subject_Date = date_info['date']
            logging.info(f"Bangumi开播日期: {anime.bangumi_subject_Date}")
        
        # 处理评分信息
        self._set_rating_data(anime, subject_data)
    
    def _set_rating_data(self, anime, subject_data: Dict[str, Any]):
        """设置评分数据"""
        if ('rating' in subject_data and
                'count' in subject_data['rating'] and
                subject_data['rating']['count'] and
                subject_data['rating']['total']):
            
            total = subject_data['rating']['total']
            score_counts = subject_data['rating']['count']
            
            # 计算加权平均评分
            weighted_sum = sum(int(score) * int(count) for score, count in score_counts.items())
            calculated_score = round(weighted_sum / total, 2)
            
            anime.score_bgm = f"{calculated_score:.2f}"
            anime.bangumi_total = str(total)
            
            logging.info(f"Bangumi评分: {anime.score_bgm}")
            logging.info(f"Bangumi评分人数: {anime.bangumi_total}")
        else:
            anime.score_bgm = 'No score available'
            logging.warning("Bangumi条目无评分信息")


# 保持向后兼容的函数接口
def extract_bangumi_data(anime, processed_name):
    """
    从Bangumi提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = BangumiExtractor()
    return extractor.extract_data(anime, processed_name) 