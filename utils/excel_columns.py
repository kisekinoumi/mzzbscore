# utils/excel_columns.py
# Excel列名配置，集中管理所有列名常量
#
# 使用说明：
# 1. 如果Excel表格的列名发生变化，只需要在这个文件中修改对应的常量值
# 2. ExcelColumns类：定义所有Excel列的名称常量
# 3. ColumnMappings类：定义平台数据的映射关系，便于批量处理
# 4. COLUMN_NAMES字典：提供字典格式的快速访问方式
#
# 例如：
# - 如果"Bangumi"列改名为"BGM评分"，只需修改ExcelColumns.BANGUMI_SCORE = "BGM评分"
# - 如果新增平台，在ExcelColumns中添加新列名，在ColumnMappings中添加映射关系
#
# 注意：修改列名后，需要确保Excel表格的实际列名与这里定义的常量保持一致

class ExcelColumns:
    """Excel列名配置类，集中定义所有列名"""
    
    # 基本信息列
    ORIGINAL_NAME = "原名"
    TRANSLATED_NAME = "译名"
    
    # 评分列
    BANGUMI_SCORE = "Bangumi"
    BANGUMI_TOTAL = "Bangumi_total"
    
    ANILIST_SCORE = "Anilist"
    ANILIST_TOTAL = "Anilist_total"
    
    MYANIMELIST_SCORE = "MyAnimelist"
    MYANIMELIST_TOTAL = "MyAnimelist_total"
    
    FILMARKS_ORIGINAL_SCORE = "Filmarks原始评分"
    FILMARKS_SCORE = "Filmarks"
    FILMARKS_TOTAL = "Filmarks_total"
    
    # 综合信息列
    COMPREHENSIVE_SCORE = "综合评分"
    RANKING = "排名"
    
    # URL列
    BANGUMI_URL = "Bangumi_url"
    ANILIST_URL = "Anilist_url"
    MYANIMELIST_URL = "Myanilist_url"
    FILMARKS_URL = "Filmarks_url"
    
    # 错误信息列
    DATE_ERROR = "Notes"


class ColumnMappings:
    """列映射配置类，定义平台数据映射关系"""
    
    # 评分数据映射
    SCORE_MAPPINGS = {
        "Bangumi": {
            "score": ExcelColumns.BANGUMI_SCORE,
            "total": ExcelColumns.BANGUMI_TOTAL
        },
        "AniList": {
            "score": ExcelColumns.ANILIST_SCORE,
            "total": ExcelColumns.ANILIST_TOTAL
        },
        "MyAnimeList": {
            "score": ExcelColumns.MYANIMELIST_SCORE,
            "total": ExcelColumns.MYANIMELIST_TOTAL
        },
        "Filmarks": {
            "original_score": ExcelColumns.FILMARKS_ORIGINAL_SCORE,
            "doubled_score": ExcelColumns.FILMARKS_SCORE,
            "total": ExcelColumns.FILMARKS_TOTAL
        }
    }
    
    # 平台链接和名称映射
    PLATFORM_URL_MAPPINGS = {
        "Bangumi": {
            "name_col": ExcelColumns.BANGUMI_URL,
            "url_col": ExcelColumns.BANGUMI_URL,
            "name_attr": "bangumi_name",
            "url_attr": "bangumi_url"
        },
        "AniList": {
            "name_col": ExcelColumns.ANILIST_URL,
            "url_col": ExcelColumns.ANILIST_URL,
            "name_attr": "anilist_name",
            "url_attr": "anilist_url"
        },
        "MyAnimeList": {
            "name_col": ExcelColumns.MYANIMELIST_URL,
            "url_col": ExcelColumns.MYANIMELIST_URL,
            "name_attr": "myanimelist_name",
            "url_attr": "myanimelist_url"
        },
        "Filmarks": {
            "name_col": ExcelColumns.FILMARKS_URL,
            "url_col": ExcelColumns.FILMARKS_URL,
            "name_attr": "filmarks_name",
            "url_attr": "filmarks_url"
        }
    }


# 提供一个快速访问的字典格式（可选）
COLUMN_NAMES = {
    'original_name': ExcelColumns.ORIGINAL_NAME,
    'translated_name': ExcelColumns.TRANSLATED_NAME,
    'bangumi_score': ExcelColumns.BANGUMI_SCORE,
    'bangumi_total': ExcelColumns.BANGUMI_TOTAL,
    'anilist_score': ExcelColumns.ANILIST_SCORE,
    'anilist_total': ExcelColumns.ANILIST_TOTAL,
    'myanimelist_score': ExcelColumns.MYANIMELIST_SCORE,
    'myanimelist_total': ExcelColumns.MYANIMELIST_TOTAL,
    'filmarks_original_score': ExcelColumns.FILMARKS_ORIGINAL_SCORE,
    'filmarks_score': ExcelColumns.FILMARKS_SCORE,
    'filmarks_total': ExcelColumns.FILMARKS_TOTAL,
    'comprehensive_score': ExcelColumns.COMPREHENSIVE_SCORE,
    'ranking': ExcelColumns.RANKING,
    'bangumi_url': ExcelColumns.BANGUMI_URL,
    'anilist_url': ExcelColumns.ANILIST_URL,
    'myanimelist_url': ExcelColumns.MYANIMELIST_URL,
    'filmarks_url': ExcelColumns.FILMARKS_URL,
    'date_error': ExcelColumns.DATE_ERROR
} 