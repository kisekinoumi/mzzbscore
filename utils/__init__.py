# utils/__init__.py
# 导入工具函数，使其可以通过utils包直接访问

# 定义__all__列表，明确指定可以从utils包中导入的内容
__all__ = [
    'fetch_data_with_retry',  # 从network模块
    'preprocess_name',         # 从text_processor模块
    'ALLOWED_YEARS',           # 从global_variables模块
    'DESIRED_YEAR',            # 从global_variables模块
    'FILE_PATH',               # 从global_variables模块
    'update_constants',        # 从global_variables模块
    'setup_logger',            # 从logger模块
    'date_error'               # 从logger模块
]

# 从network模块导入
from utils.network import fetch_data_with_retry

# 从text_processor模块导入
from utils.text_processor import preprocess_name

# 从global_variables模块导入
from utils.global_variables import ALLOWED_YEARS, DESIRED_YEAR, FILE_PATH, update_constants

# 从logger模块导入
from utils.logger import setup_logger, date_error
