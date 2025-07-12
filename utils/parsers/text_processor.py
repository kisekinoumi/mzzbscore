# utils/text_processor.py
# 存放文本处理相关的工具函数

import re

def preprocess_name(original_name):
    """
    预处理原始名称，将特殊符号替换为空格。

    Args:
        original_name (str): 原始名称

    Returns:
        str: 处理后的名称
    """
    #  去除特殊字符
    cleaned_name = re.sub(r'[-*@#\.\+]', ' ', str(original_name), flags=re.UNICODE)
    # 将多个连续空格替换为单个空格
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    return cleaned_name