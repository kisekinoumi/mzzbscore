import logging
import sys

def setup_logger(log_file_path='mzzb_score.log'):
    """
    配置并返回日志记录器
    
    Args:
        log_file_path: 日志文件路径，默认为'mzzb_score.log'
        
    Returns:
        配置好的logger对象
    """
    # 配置日志
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler(log_file_path, mode='w', encoding='utf-8'),  # 'w' 覆盖模式
                            logging.StreamHandler(sys.stdout)  # 同时输出到控制台
                        ])
    
    return logging.getLogger()

# 全局日期错误列表
date_error = []  # 用于存储日期错误信息