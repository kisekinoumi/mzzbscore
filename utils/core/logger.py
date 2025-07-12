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
    # 设置控制台输出编码，启用行缓冲
    console_handler = logging.StreamHandler()
    if sys.platform == 'win32':
        # 在Windows系统中，特别是exe环境中，确保控制台输出使用UTF-8编码
        console_handler.stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    else:
        # 设置行缓冲模式，确保及时输出
        console_handler.stream = sys.stdout
        sys.stdout.reconfigure(line_buffering=True)
    
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

def setup_interactive_logger():
    """
    设置交互式logger，用于用户交互场景（如Twitter配置）
    特点：无时间戳格式，实时输出，既显示到控制台也记录到文件
    
    Returns:
        配置好的交互式logger对象
    """
    # 创建专门的交互式logger
    interactive_logger = logging.getLogger('interactive')
    interactive_logger.setLevel(logging.INFO)
    
    # 避免重复添加handler
    if interactive_logger.handlers:
        return interactive_logger
    
    # 控制台handler - 无格式，实时输出
    console_handler = logging.StreamHandler()
    if sys.platform == 'win32':
        console_handler.stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    else:
        console_handler.stream = sys.stdout
        sys.stdout.reconfigure(line_buffering=True)
    
    # 设置无格式的formatter，直接输出消息
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    
    # 文件handler - 带格式，用于日志记录
    file_handler = logging.FileHandler('mzzb_score.log', mode='a', encoding='utf-8')
    file_formatter = logging.Formatter('%(asctime)s - INTERACTIVE - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # 添加handlers
    interactive_logger.addHandler(console_handler)
    interactive_logger.addHandler(file_handler)
    
    # 防止向父logger传播，避免重复输出
    interactive_logger.propagate = False
    
    return interactive_logger

# 全局日期错误列表
date_error = []  # 用于存储日期错误信息