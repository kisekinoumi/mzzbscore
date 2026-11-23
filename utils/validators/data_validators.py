# utils/validators/data_validators.py
# 数据验证相关的工具函数

# 定义不可用值的常量（覆盖所有提取器错误状态码与占位文本）
UNAVAILABLE_VALUES = [
    "No score available",
    "No results found",
    "No acceptable subject found",
    "",
    None,
    "No href found",
    "No Filmarks score found",
    "No Filmarks results",
    "N/A",
    "NaN",
    "No score found",
    "No count found",
    "No vote data available",
    "No AniList results",
    "Error with AniList API",
    "No response results",
    "Request failed",
    "Parse error",
    "Invalid subject ID",
    "Invalid anime ID",
    "Missing MAL API config",
    "Not an anime subject",
]

# 无效名称常量
INVALID_NAMES = ["No name found", "未知名称", "", None]


def is_valid_value(value):
    """
    判断值是否有效（不在不可用值列表中）
    """
    if isinstance(value, str):
        value = value.strip()
    return value not in UNAVAILABLE_VALUES


def is_valid_name(name):
    """
    判断名称是否有效
    """
    if isinstance(name, str):
        name = name.strip()
    return name not in INVALID_NAMES


def safe_float(value):
    """
    安全地将值转换为float，如果无法转换则返回None
    """
    if value in UNAVAILABLE_VALUES:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value):
    """
    安全地将值转换为int，如果无法转换则返回None
    """
    if value in UNAVAILABLE_VALUES:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(value)
    except (ValueError, TypeError):
        return None


def validate_score_range(score, min_val=0, max_val=10):
    """
    验证评分是否在有效范围内
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
    """
    if not url or url in UNAVAILABLE_VALUES:
        return False
    return isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))


def sanitize_anime_name(name):
    """
    清理动画名称，去除无效字符
    """
    if not name or name in INVALID_NAMES:
        return None

    cleaned_name = str(name).strip()
    if not cleaned_name or cleaned_name in INVALID_NAMES:
        return None

    return cleaned_name


def validate_anime_data(anime):
    """
    验证动画数据的完整性
    """
    validation_result = {
        "original_name": bool(anime.original_name),
        "scores": {
            "bangumi": is_valid_value(anime.score_bgm),
            "anilist": is_valid_value(anime.score_al),
            "myanimelist": is_valid_value(anime.score_mal),
            "filmarks": is_valid_value(anime.score_fm),
        },
        "names": {
            "bangumi": is_valid_name(anime.bangumi_name),
            "anilist": is_valid_name(anime.anilist_name),
            "myanimelist": is_valid_name(anime.myanimelist_name),
            "filmarks": is_valid_name(anime.filmarks_name),
        },
        "urls": {
            "bangumi": validate_url(anime.bangumi_url),
            "anilist": validate_url(anime.anilist_url),
            "myanimelist": validate_url(anime.myanimelist_url),
            "filmarks": validate_url(anime.filmarks_url),
        },
    }

    valid_scores_count = sum(validation_result["scores"].values())
    valid_urls_count = sum(validation_result["urls"].values())

    validation_result["summary"] = {
        "valid_scores_count": valid_scores_count,
        "valid_urls_count": valid_urls_count,
        "has_any_valid_data": valid_scores_count > 0 or valid_urls_count > 0,
    }

    return validation_result
