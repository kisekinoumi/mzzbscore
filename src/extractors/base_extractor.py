# src/extractors/base_extractor.py
# 基础数据提取器，包含各平台通用的提取逻辑

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from src.data_process.matcher import select_best_candidate


class BaseExtractor(ABC):
    """基础数据提取器抽象类"""

    def __init__(self, platform_name: str, score_key: Optional[str] = None):
        self.platform_name = platform_name
        self.platform_key = platform_name.lower()
        self.score_key = score_key or self.platform_key

    def extract_data(self, anime, processed_name: str) -> bool:
        """
        统一的数据提取入口
        Args:
            anime: Anime对象
            processed_name: 预处理后的名称
        Returns:
            bool: 是否成功提取数据
        """
        url_attr = f"{self.platform_key}_url"
        existing_url = getattr(anime, url_attr, None)

        if existing_url:
            identifier = self.extract_identifier_from_url(existing_url)
            if identifier:
                logging.info(f"使用已有{self.platform_name}链接提取数据: {existing_url}")
                return self.extract_by_identifier(anime, identifier)

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
    """候选条目验证器，委托给结构化标题与多维置信度匹配引擎"""

    @staticmethod
    def validate_candidates(
        candidates: List[Any],
        extract_candidate_info: Callable,
        platform_name: str,
        max_attempts: int = 8,
        anime: Any = None,
        query: Optional[str] = None,
        platform_key: str = "",
        log_failure: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        验证候选条目并返回综合年份、季数/衍生词门控与标题相似度的最优候选
        """
        return select_best_candidate(
            candidates=candidates,
            extract_candidate_info=extract_candidate_info,
            platform_name=platform_name,
            platform_key=platform_key,
            anime=anime,
            query=query,
            max_attempts=max_attempts,
            log_failure=log_failure,
        )


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
    def handle_no_acceptable_candidate_error(
        anime,
        platform_key: str,
        error_message: str = "No acceptable subject found",
    ) -> bool:
        """处理未找到符合要求候选条目的错误"""
        setattr(anime, f"score_{platform_key}", error_message)
        return False


class ExtractorLogger:
    """提取器日志记录器"""

    @staticmethod
    def log_extraction_result(anime, platform_name: str, platform_key: str):
        """记录提取结果"""
        platform_lower = platform_name.lower()
        url_attr = f"{platform_lower}_url"
        name_attr = f"{platform_lower}_name"
        score_attr = f"score_{platform_key}"
        total_attr = f"{platform_lower}_total"
        date_attr = f"{platform_lower}_subject_Date"

        logging.info(f"{platform_name}链接: {getattr(anime, url_attr, 'N/A')}")
        logging.info(f"{platform_name}名称: {getattr(anime, name_attr, 'N/A')}")
        logging.info(f"{platform_name}评分: {getattr(anime, score_attr, 'N/A')}")

        total_value = getattr(anime, total_attr, None)
        if total_value:
            logging.info(f"{platform_name}评分人数: {total_value}")

        date_value = getattr(anime, date_attr, None)
        if date_value:
            logging.info(f"{platform_name}开播日期: {date_value}")

    @staticmethod
    def log_twitter_info(anime):
        """记录Twitter信息"""
        if hasattr(anime, "twitter_username") and anime.twitter_username:
            logging.info(
                f"Twitter账号: @{anime.twitter_username} ({getattr(anime, 'twitter_url', 'N/A')})"
            )


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
        from utils.core.global_variables import get_allowed_years

        allowed_years = get_allowed_years()
        return year in allowed_years if year else False
