# utils/core/global_variables.py
# 存放全局配置变量与目标季度解析逻辑

import re
from typing import List, Optional

# 全局变量，将在程序运行时设置
ALLOWED_YEARS: List[str] = []
DESIRED_YEAR: str = ""
DESIRED_MONTH: Optional[int] = None
FILE_PATH: str = "mzzb.xlsx"

_YEAR_RE = re.compile(r"((?:19|20)\d{2})")
_YEAR_MONTH_RE = re.compile(r"(?:19|20)\d{2}\s*年\s*(1[0-2]|0?[1-9])\s*月")


def update_constants(year_or_header: str) -> None:
    """
    更新全局目标年份与可选目标月份常量。
    兼容传入纯年份字符串（如 "2026"）或完整表头文本（如 "2026年04月新番首月评分"）。

    Args:
        year_or_header: 年份字符串或 Excel A1 单元格文本
    """
    global ALLOWED_YEARS, DESIRED_YEAR, DESIRED_MONTH

    text = str(year_or_header or "").strip()
    year_match = _YEAR_RE.search(text)
    if year_match:
        year_str = year_match.group(1)
    else:
        candidate = text[:4]
        year_str = candidate if candidate.isdigit() else ""

    DESIRED_YEAR = year_str
    if year_str.isdigit():
        ALLOWED_YEARS = [year_str, str(int(year_str) - 1)]
    else:
        ALLOWED_YEARS = []

    month_match = _YEAR_MONTH_RE.search(text)
    if month_match:
        DESIRED_MONTH = int(month_match.group(1))
    else:
        DESIRED_MONTH = None


def get_allowed_years() -> List[str]:
    """获取允许的年份列表（如 ['2026', '2025']）"""
    return ALLOWED_YEARS


def get_desired_year() -> str:
    """获取目标年份（如 '2026'）"""
    return DESIRED_YEAR


def get_desired_month() -> Optional[int]:
    """获取从表头解析出的目标开播月份（如 4），未指定时返回 None"""
    return DESIRED_MONTH


def get_desired_quarter_index() -> Optional[int]:
    """获取目标季度序号（year * 4 + quarter_0_to_3），未指定月份时返回 None"""
    if DESIRED_YEAR and DESIRED_YEAR.isdigit() and DESIRED_MONTH:
        return int(DESIRED_YEAR) * 4 + (DESIRED_MONTH - 1) // 3
    return None
