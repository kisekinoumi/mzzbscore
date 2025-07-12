# biz/extractors/anilist_refactored.py
# 重构后的AniList数据提取逻辑

import logging
from typing import Optional, Dict, Any
from utils import fetch_data_with_retry, LinkParser, TwitterParser
from .base_extractor import BaseExtractor, CandidateValidator, ExtractorErrorHandler, ExtractorLogger, DateExtractor


class AniListExtractor(BaseExtractor):
    """AniList数据提取器"""
    
    def __init__(self):
        super().__init__("AniList")
        self.api_url = 'https://graphql.anilist.co'
    
    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从AniList URL中提取anime ID"""
        return LinkParser.extract_anilist_id(url)
    
    def extract_by_identifier(self, anime, anime_id: str) -> bool:
        """通过anime_id直接从AniList API提取数据"""
        try:
            anime_id_int = int(anime_id)
        except ValueError:
            return ExtractorErrorHandler.handle_parse_error(anime, "al", "Invalid anime ID")
        
        # 获取基本信息
        basic_info = self._fetch_basic_info(anime_id_int)
        if not basic_info:
            return ExtractorErrorHandler.handle_request_error(anime, "al")
        
        # 设置基本信息
        self._set_basic_info(anime, anime_id_int, basic_info)
        
        # 获取详细信息
        detail_info = self._fetch_detail_info(anime_id_int)
        if detail_info:
            self._set_detail_info(anime, detail_info)
        else:
            ExtractorErrorHandler.handle_request_error(anime, "al", "No response results")
        
        # 记录日志
        ExtractorLogger.log_extraction_result(anime, self.platform_name, "al")
        ExtractorLogger.log_twitter_info(anime)
        return True
    
    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索从AniList API提取数据"""
        # 搜索候选条目
        candidates = self._search_candidates(processed_name)
        if not candidates:
            return ExtractorErrorHandler.handle_no_results_error(anime, "al", "No AniList results")
        
        # 验证候选条目
        selected_candidate = CandidateValidator.validate_candidates(
            candidates=candidates,
            extract_candidate_info=self._extract_candidate_info,
            platform_name=self.platform_name,
            max_attempts=5
        )
        
        if not selected_candidate:
            return ExtractorErrorHandler.handle_no_acceptable_candidate_error(anime, "al")
        
        # 使用选中的候选条目
        anime_id = selected_candidate['id']
        anime.anilist_url = f"https://anilist.co/anime/{anime_id}"
        anime.anilist_name = selected_candidate['name']
        anime.anilist_subject_Date = selected_candidate['date']
        
        # 获取详细信息
        detail_info = self._fetch_detail_info(anime_id)
        if detail_info:
            self._set_detail_info(anime, detail_info)
        else:
            ExtractorErrorHandler.handle_request_error(anime, "al", "Request failed")
        
        # 记录日志
        ExtractorLogger.log_extraction_result(anime, self.platform_name, "al")
        ExtractorLogger.log_twitter_info(anime)
        return True
    
    def _fetch_basic_info(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """获取基本信息"""
        query = '''
        query ($id: Int) {
          Media (id: $id) {
            id
            title {
              native
            }
            startDate {
              year
              month
            }
          }
        }
        '''
        variables = {"id": anime_id}
        
        response = fetch_data_with_retry(
            self.api_url, 
            method='POST', 
            data={'query': query, 'variables': variables}
        )
        
        if not response:
            return None
        
        try:
            data = response.json()
            return data.get('data', {}).get('Media')
        except Exception:
            logging.error(f"AniList条目 {anime_id} JSON解析失败")
            return None
    
    def _fetch_detail_info(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """获取详细信息（评分、评分人数、外部链接）"""
        query = '''
        query ($id: Int) {
          Media (id: $id) {
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
          }
        }
        '''
        variables = {"id": anime_id}
        
        response = fetch_data_with_retry(
            self.api_url, 
            method='POST',
            data={'query': query, 'variables': variables}
        )
        
        if not response:
            return None
        
        try:
            data = response.json()
            return data.get('data', {}).get('Media')
        except Exception:
            logging.warning("AniList详细数据解析失败")
            return None
    
    def _search_candidates(self, processed_name: str) -> Optional[list]:
        """搜索候选条目"""
        query = '''
        query ($search: String) {
          Page (page: 1, perPage: 5) {
            media (search: $search, type: ANIME) {
              id
              title {
                native
              }
              startDate {
                year
                month
              }
            }
          }
        }
        '''
        variables = {"search": processed_name}
        
        response = fetch_data_with_retry(
            self.api_url, 
            method='POST', 
            data={'query': query, 'variables': variables}
        )
        
        if not response:
            return None
        
        try:
            data = response.json()
            return data.get('data', {}).get('Page', {}).get('media', [])
        except Exception:
            logging.error("AniList搜索结果JSON解析失败")
            return None
    
    def _extract_candidate_info(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取候选条目信息"""
        try:
            name = candidate['title']['native']
            start_date = candidate.get('startDate', {})
            year = str(start_date.get('year')) if start_date.get('year') else None
            candidate_id = candidate['id']
            
            # 构建日期字符串
            date_str = None
            if year:
                month = start_date.get('month')
                if month:
                    date_str = f"{year}{month:02d}"
                else:
                    date_str = year
            
            return {
                'name': name,
                'year': year,
                'id': candidate_id,
                'date': date_str,
                'data': candidate
            }
        except (KeyError, TypeError):
            return None
    
    def _set_basic_info(self, anime, anime_id: int, basic_info: Dict[str, Any]):
        """设置基本信息"""
        anime.anilist_url = f"https://anilist.co/anime/{anime_id}"
        anime.anilist_name = basic_info['title']['native']
        
        # 处理开播日期
        start_date = basic_info.get('startDate', {})
        if start_date.get('year'):
            year = str(start_date['year'])
            month = start_date.get('month')
            if month:
                anime.anilist_subject_Date = f"{year}{month:02d}"
            else:
                anime.anilist_subject_Date = year
            logging.info(f"AniList开播日期: {anime.anilist_subject_Date}")
    
    def _set_detail_info(self, anime, detail_info: Dict[str, Any]):
        """设置详细信息（评分、评分人数、Twitter）"""
        # 设置评分
        anime.score_al = detail_info.get('averageScore', 'No score found')
        
        # 计算评分人数
        total_votes = 0
        stats = detail_info.get('stats', {})
        score_distribution = stats.get('scoreDistribution', [])
        
        if score_distribution:
            for score_data in score_distribution:
                amount = score_data.get('amount', 0)
                if amount:
                    total_votes += amount
            anime.anilist_total = str(total_votes)
            
        else:
            anime.anilist_total = 'No vote data available'
            logging.warning("无法获取AniList评分分布数据")
        
        # 提取Twitter信息
        external_links = detail_info.get('externalLinks', [])
        if external_links:
            twitter_info = TwitterParser.extract_twitter_from_external_links(external_links)
            if twitter_info:
                anime.twitter_username = twitter_info.get('twitter_username', '')
                anime.twitter_url = twitter_info.get('twitter_url', '')
            else:
                logging.info("AniList条目中未找到Twitter链接")
        else:
            logging.info("AniList条目中没有外部链接信息")


# 保持向后兼容的函数接口
def extract_anilist_data(anime, processed_name):
    """
    从AniList提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    extractor = AniListExtractor()
    return extractor.extract_data(anime, processed_name) 