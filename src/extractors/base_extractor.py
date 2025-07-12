# biz/extractors/base_extractor.py
# 基础数据提取器，包含各平台通用的提取逻辑

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable


class BaseExtractor(ABC):
    """基础数据提取器抽象类"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.platform_key = platform_name.lower()
    
    def extract_data(self, anime, processed_name: str) -> bool:
        """
        统一的数据提取入口
        Args:
            anime: Anime对象
            processed_name: 预处理后的名称
        Returns:
            bool: 是否成功提取数据
        """
        # 检查是否已有URL
        url_attr = f"{self.platform_key}_url"
        existing_url = getattr(anime, url_attr, None)
        
        if existing_url:
            identifier = self.extract_identifier_from_url(existing_url)
            if identifier:
                logging.info(f"使用已有{self.platform_name}链接提取数据: {existing_url}")
                return self.extract_by_identifier(anime, identifier)
        
        # 如果没有链接，则进行搜索
        logging.info(f"通过搜索获取{self.platform_name}数据: {processed_name}")
        return self.extract_by_search(anime, processed_name)
    
    @abstractmethod
    def extract_identifier_from_url(self, url: str) -> Optional[str]:
        """从URL中提取标识符（ID等）"""
        pass
    
    @abstractmethod
    def extract_by_identifier(self, anime, identifier: str) -> bool:
        """通过标识符直接提取数据"""
        pass
    
    @abstractmethod
    def extract_by_search(self, anime, processed_name: str) -> bool:
        """通过搜索提取数据"""
        pass


class CandidateValidator:
    """候选条目验证器，处理年份验证逻辑"""
    
    @staticmethod
    def validate_candidates(candidates: List[Any], 
                          extract_candidate_info: Callable,
                          platform_name: str,
                          max_attempts: int = 5) -> Optional[Dict[str, Any]]:
        """
        验证候选条目并返回符合年份要求的第一个候选
        Args:
            candidates: 候选条目列表
            extract_candidate_info: 提取候选条目信息的回调函数，返回{"name": str, "year": str, "id": str, "data": Any}
            platform_name: 平台名称（用于日志）
            max_attempts: 最大尝试次数
        Returns:
            dict or None: 符合要求的候选条目信息，找不到时返回None
        """
        candidate_found = False
        selected_candidate = None
        attempts = 0
        
        for candidate in candidates:
            attempts += 1
            if attempts > max_attempts:
                break
            
            try:
                candidate_info = extract_candidate_info(candidate)
                if not candidate_info:
                    continue
                
                candidate_name = candidate_info.get('name', '未知名称')
                candidate_year = candidate_info.get('year')
                candidate_id = candidate_info.get('id')
                
                # 动态获取ALLOWED_YEARS，避免导入陷阱
                from utils.core.global_variables import get_allowed_years
                allowed_years = get_allowed_years()
                if candidate_year and candidate_year in allowed_years:
                    candidate_found = True
                    selected_candidate = candidate_info
                    logging.info(f"选中{platform_name}候选条目名称为 {candidate_name}，选中{platform_name}候选条目 {candidate_id}，放送年份: {candidate_year}")
                    break
                else:
                    logging.info(f"选中{platform_name}候选条目名称为 {candidate_name}，{platform_name}候选条目的放送年份 {candidate_year} 不符合要求")
                    
            except Exception as e:
                logging.warning(f"{platform_name}候选条目 {attempts} 处理失败: {e}")
                continue
        
        if not candidate_found:
            logging.error(f"尝试{max_attempts}次后，没有找到放送年份符合要求的 {platform_name} 候选条目")
            return None
        
        return selected_candidate


class ExtractorErrorHandler:
    """提取器错误处理器"""
    
    @staticmethod
    def handle_request_error(anime, platform_key: str, error_message: str = "Request failed") -> bool:
        """处理请求错误"""
        setattr(anime, f"score_{platform_key}", error_message)
        return False
    
    @staticmethod
    def handle_parse_error(anime, platform_key: str, error_message: str = "Parse error") -> bool:
        """处理解析错误"""
        setattr(anime, f"score_{platform_key}", error_message)
        return False
    
    @staticmethod
    def handle_no_results_error(anime, platform_key: str, error_message: str = "No results found") -> bool:
        """处理无结果错误"""
        setattr(anime, f"score_{platform_key}", error_message)
        return False
    
    @staticmethod
    def handle_no_acceptable_candidate_error(anime, platform_key: str, error_message: str = "No acceptable subject found") -> bool:
        """处理未找到符合要求候选条目的错误"""
        setattr(anime, f"score_{platform_key}", error_message)
        return False


class ExtractorLogger:
    """提取器日志记录器"""
    
    @staticmethod
    def log_extraction_result(anime, platform_name: str, platform_key: str):
        """记录提取结果"""
        # 使用完整平台名称的小写作为属性名（与实际设置的属性名一致）
        platform_lower = platform_name.lower()
        url_attr = f"{platform_lower}_url"
        name_attr = f"{platform_lower}_name"
        score_attr = f"score_{platform_key}"
        total_attr = f"{platform_lower}_total"
        date_attr = f"{platform_lower}_subject_Date"
        
        logging.info(f"{platform_name}链接: {getattr(anime, url_attr, 'N/A')}")
        logging.info(f"{platform_name}名称: {getattr(anime, name_attr, 'N/A')}")
        logging.info(f"{platform_name}评分: {getattr(anime, score_attr, 'N/A')}")
        
        # 记录评分人数（如果存在）
        total_value = getattr(anime, total_attr, None)
        if total_value:
            logging.info(f"{platform_name}评分人数: {total_value}")
        
        # 记录开播日期（如果存在）
        date_value = getattr(anime, date_attr, None)
        if date_value:
            logging.info(f"{platform_name}开播日期: {date_value}")
    
    @staticmethod
    def log_twitter_info(anime):
        """记录Twitter信息"""
        if hasattr(anime, 'twitter_username') and anime.twitter_username:
            logging.info(f"Twitter账号: @{anime.twitter_username} ({getattr(anime, 'twitter_url', 'N/A')})")


class DateExtractor:
    """日期提取器，包含各平台的日期提取逻辑"""
    
    @staticmethod
    def extract_year_from_yyyymm(date_str: str) -> Optional[str]:
        """从YYYYMM格式中提取年份"""
        if date_str and len(date_str) >= 4:
            return date_str[:4]
        return None
    
    @staticmethod
    def validate_year_in_allowed(year: str) -> bool:
        """验证年份是否在允许范围内"""
        # 动态获取ALLOWED_YEARS，避免导入陷阱
        from utils.core.global_variables import get_allowed_years
        allowed_years = get_allowed_years()
        return year in allowed_years if year else False 