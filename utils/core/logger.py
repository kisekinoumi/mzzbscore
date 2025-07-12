# -*- coding: utf-8 -*-
import logging
import sys
import io

def setup_logger(log_file_path='mzzb_score.log'):
    """
    配置并返回日志记录器
    
    Args:
        log_file_path: 日志文件路径，默认为'mzzb_score.log'
        
    Returns:
        配置好的logger对象
    """
    # 设置控制台输出编码
    console_handler = logging.StreamHandler()
    if sys.platform == 'win32':
        # 在Windows系统中，特别是exe环境中，确保控制台输出使用UTF-8编码
        console_handler.stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    # 配置日志
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler(log_file_path, mode='w', encoding='utf-8'),  # 文件输出UTF-8
                            console_handler  # 控制台输出UTF-8
                        ])
    
    # 控制第三方库的详细日志输出
    # 禁用 httpx 的详细HTTP请求日志
    logging.getLogger('httpx').setLevel(logging.WARNING)
    # 禁用 httpcore 的详细日志
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    # 控制 requests 库的详细日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    # 控制 asyncio 的详细日志
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    return logging.getLogger()

# 全局日期错误列表
date_error = []  # 用于存储日期错误信息