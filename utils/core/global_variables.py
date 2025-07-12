# utils/global_variables.py
# 存放全局变量

# 全局变量，将在程序运行时设置
ALLOWED_YEARS = []
DESIRED_YEAR = ""
FILE_PATH = 'mzzb.xlsx'

def update_constants(year):
    """
    更新全局变量
    
    Args:
        year (str): 目标年份
    """
    global ALLOWED_YEARS, DESIRED_YEAR
    DESIRED_YEAR = year
    ALLOWED_YEARS = [DESIRED_YEAR, str(int(DESIRED_YEAR) - 1)]  # 例如 ["2025", "2024"]


def get_allowed_years():
    """
    获取允许的年份列表
    
    Returns:
        list: 允许的年份列表
    """
    return ALLOWED_YEARS


def get_desired_year():
    """
    获取目标年份
    
    Returns:
        str: 目标年份
    """
    return DESIRED_YEAR