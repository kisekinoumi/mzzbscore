"""
网络工具模块
"""

from .network import *
from .proxy_config import setup_proxy, get_global_proxy, has_proxy, get_proxy_status, reset_proxy

__all__ = ['setup_proxy', 'get_global_proxy', 'has_proxy', 'get_proxy_status', 'reset_proxy'] 