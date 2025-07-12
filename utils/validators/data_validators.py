# utils/data_validators.py
# 数据验证相关的工具函数

import logging


# 定义不可用值的常量
UNAVAILABLE_VALUES = [
    'No score available', 'No results found', '', None,
    'No href found', 'No Filmarks score found', 'No Filmarks results',
    'N/A', 'No score found', 'No AniList results',
    'Error with AniList API', 'No response results'
]

# 无效名称常量
INVALID_NAMES = ['No name found', None]


def is_valid_value(value):
    """
    判断值是否有效（不在不可用值列表中）
    Args:
        value: 要检查的值
    Returns:
        bool: 值是否有效
    """
    return value not in UNAVAILABLE_VALUES


def is_valid_name(name):
    """
    判断名称是否有效
    Args:
        name: 要检查的名称
    Returns:
        bool: 名称是否有效
    """
    return name not in INVALID_NAMES


def safe_float(value):
    """
    安全地将值转换为float，如果无法转换则返回None
    Args:
        value: 要转换的值
    Returns:
        float or None: 转换后的浮点数，失败时返回None
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value):
    """
    安全地将值转换为int，如果无法转换则返回None
    Args:
        value: 要转换的值
    Returns:
        int or None: 转换后的整数，失败时返回None
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def validate_score_range(score, min_val=0, max_val=10):
    """
    验证评分是否在有效范围内
    Args:
        score: 评分值
        min_val: 最小值（默认0）
        max_val: 最大值（默认10）
    Returns:
        bool: 评分是否在有效范围内
    """
    if score is None:
        return False
    try:
        score_float = float(score)
        return min_val <= score_float <= max_val
    except (ValueError, TypeError):
        return False


def validate_url(url):
    """
    简单验证URL是否有效
    Args:
        url: 要验证的URL
    Returns:
        bool: URL是否有效
    """
    if not url or url in UNAVAILABLE_VALUES:
        return False
    return isinstance(url, str) and (url.startswith('http://') or url.startswith('https://'))


def sanitize_anime_name(name):
    """
    清理动画名称，去除无效字符
    Args:
        name: 原始名称
    Returns:
        str or None: 清理后的名称，如果无效返回None
    """
    if not name or name in INVALID_NAMES:
        return None
    
    # 去除首尾空白字符
    cleaned_name = str(name).strip()
    
    # 如果清理后为空，返回None
    if not cleaned_name:
        return None
        
    return cleaned_name


def validate_anime_data(anime):
    """
    验证动画数据的完整性
    Args:
        anime: Anime对象
    Returns:
        dict: 验证结果，包含各项数据的有效性
    """
    validation_result = {
        'original_name': bool(anime.original_name),
        'scores': {
            'bangumi': is_valid_value(anime.score_bgm),
            'anilist': is_valid_value(anime.score_al),
            'myanimelist': is_valid_value(anime.score_mal),
            'filmarks': is_valid_value(anime.score_fm)
        },
        'names': {
            'bangumi': is_valid_name(anime.bangumi_name),
            'anilist': is_valid_name(anime.anilist_name),
            'myanimelist': is_valid_name(anime.myanimelist_name),
            'filmarks': is_valid_name(anime.filmarks_name)
        },
        'urls': {
            'bangumi': validate_url(anime.bangumi_url),
            'anilist': validate_url(anime.anilist_url),
            'myanimelist': validate_url(anime.myanimelist_url),
            'filmarks': validate_url(anime.filmarks_url)
        }
    }
    
    # 计算有效数据源数量
    valid_scores_count = sum(validation_result['scores'].values())
    valid_urls_count = sum(validation_result['urls'].values())
    
    validation_result['summary'] = {
        'valid_scores_count': valid_scores_count,
        'valid_urls_count': valid_urls_count,
        'has_any_valid_data': valid_scores_count > 0 or valid_urls_count > 0
    }
    
    return validation_result 