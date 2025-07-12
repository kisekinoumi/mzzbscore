# utils/network/proxy_config.py
# 代理配置模块，包含自动检测Windows系统代理、推特验证和降级处理

import winreg
import requests
import logging
import time
from typing import Optional, Dict, Any


# 全局代理配置
_global_proxy = None


def get_system_proxy() -> Optional[Dict[str, str]]:
    """
    自动检测Windows系统代理设置
    Returns:
        Dict[str, str] or None: 代理配置字典，失败时返回None
    """
    try:
        # 打开注册表项
        reg_key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        )
        
        try:
            # 检查代理是否启用
            proxy_enable, _ = winreg.QueryValueEx(reg_key, "ProxyEnable")
            if not proxy_enable:
                logging.info("系统代理未启用")
                return None
            
            # 读取代理服务器设置
            proxy_server, _ = winreg.QueryValueEx(reg_key, "ProxyServer")
            
            if proxy_server:
                # 解析代理服务器地址
                if "=" in proxy_server:
                    # 格式: http=127.0.0.1:7890;https=127.0.0.1:7890
                    proxy_dict = {}
                    for item in proxy_server.split(";"):
                        if "=" in item:
                            protocol, address = item.split("=", 1)
                            proxy_dict[protocol] = f"http://{address}"
                    
                    # 确保至少有http代理
                    if "http" not in proxy_dict and "https" in proxy_dict:
                        proxy_dict["http"] = proxy_dict["https"]
                    elif "https" not in proxy_dict and "http" in proxy_dict:
                        proxy_dict["https"] = proxy_dict["http"]
                    
                    return proxy_dict
                else:
                    # 格式: 127.0.0.1:7890
                    proxy_url = f"http://{proxy_server}"
                    return {"http": proxy_url, "https": proxy_url}
            
        finally:
            winreg.CloseKey(reg_key)
            
    except FileNotFoundError:
        logging.info("未找到系统代理设置")
        return None
    except Exception as e:
        logging.warning(f"读取系统代理设置失败: {e}")
        return None
    
    return None


def verify_proxy_twitter(proxy_dict: Dict[str, str]) -> bool:
    """
    验证代理是否可用 - 通过请求推特验证
    Args:
        proxy_dict: 代理配置字典
    Returns:
        bool: 代理是否可用
    """
    # 推特相关的测试URL（按优先级排序）
    twitter_test_urls = [
        "https://x.com",
        "https://twitter.com", 
        "https://api.twitter.com",
    ]
    
    for test_url in twitter_test_urls:
        try:
            logging.info(f"尝试通过代理访问: {test_url}")
            
            response = requests.get(
                test_url, 
                proxies=proxy_dict, 
                timeout=5,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                },
                allow_redirects=True
            )
            
            if response.status_code == 200:
                logging.info(f"✅ 代理验证成功，可以正常访问 {test_url}")
                return True
            elif response.status_code in [301, 302, 303, 307, 308]:
                # 重定向也算成功
                logging.info(f"✅ 代理验证成功，{test_url} 返回重定向")
                return True
                
        except requests.exceptions.ProxyError:
            logging.warning(f"❌ 代理连接失败: {test_url}")
            continue
        except requests.exceptions.Timeout:
            logging.warning(f"❌ 代理访问超时: {test_url}")
            continue
        except requests.exceptions.ConnectionError:
            logging.warning(f"❌ 代理连接错误: {test_url}")
            continue
        except Exception as e:
            logging.warning(f"❌ 访问 {test_url} 异常: {e}")
            continue
    
    logging.warning("❌ 所有推特URL都无法通过代理访问")
    return False


def setup_proxy() -> Optional[Dict[str, str]]:
    """
    设置代理配置，使用推特验证，包含降级处理
    Returns:
        Dict[str, str] or None: 代理配置字典，失败时返回None
    """
    global _global_proxy
    
    logging.info("🔍 开始检测系统代理...")
    
    # 1. 尝试检测系统代理
    system_proxy = get_system_proxy()
    
    if system_proxy:
        logging.info(f"检测到系统代理: {system_proxy.get('http', 'N/A')}")
        
        # 2. 使用推特验证代理可用性
        if verify_proxy_twitter(system_proxy):
            logging.info("✅ 代理验证成功，可以正常访问推特，所有网络请求将使用代理")
            _global_proxy = system_proxy
            return system_proxy
        else:
            logging.warning("❌ 代理无法访问推特，降级为直连模式")
            _global_proxy = None
            return None
    else:
        logging.info("未检测到系统代理，使用直连模式")
        _global_proxy = None
        return None


def get_global_proxy() -> Optional[Dict[str, str]]:
    """
    获取全局代理配置
    Returns:
        Dict[str, str] or None: 全局代理配置
    """
    return _global_proxy


def reset_proxy():
    """重置代理配置"""
    global _global_proxy
    _global_proxy = None


def has_proxy() -> bool:
    """检查是否有可用的代理"""
    return _global_proxy is not None


def get_proxy_status() -> str:
    """获取代理状态描述"""
    if has_proxy():
        return f"使用代理: {_global_proxy.get('http', 'N/A')}"
    else:
        return "直连模式" 