# extractors/__init__.py
# 使extractors成为一个Python包

from .bangumi import extract_bangumi_data
from .myanimelist import extract_myanimelist_data
from .anilist import extract_anilist_data
from .filmarks import extract_filmarks_data
from .twitter import TwitterFollowersHelper

# 导入基础提取器组件
from .base_extractor import BaseExtractor, CandidateValidator, ExtractorErrorHandler, ExtractorLogger

__all__ = [
    'extract_bangumi_data',
    'extract_myanimelist_data',
    'extract_anilist_data',
    'extract_filmarks_data',
    'TwitterFollowersHelper',
    'BaseExtractor',
    'CandidateValidator',
    'ExtractorErrorHandler',
    'ExtractorLogger'
]