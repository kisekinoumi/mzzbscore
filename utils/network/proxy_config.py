# utils/network/proxy_config.py
# 代理配置模块，包含自动检测Windows系统代理、推特验证和降级处理

try:
    import winreg
except ImportError:
    winreg = None
import requests
import logging
import time
from typing import Optional, Dict, Any


# 全局代理配置
_global_proxy = None

# Twitter可用性状态
_twitter_accessible = True


def get_system_proxy() -> Optional[Dict[str, str]]:
    """
    自动检测Windows系统代理设置
    Returns:
        Dict[str, str] or None: 代理配置字典，失败时返回None
    """
    try:
        if winreg is None:
            logging.info("当前非Windows系统，跳过系统代理自动检测")
            return None
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
    # 主要的Twitter测试URL
    main_twitter_urls = [
        "https://twitter.com",
        "https://x.com"
    ]
    
    # 备用测试URL
    backup_url = "https://google.com"
    
    success_count = 0
    total_main_urls = len(main_twitter_urls)
    
    # 测试主要的Twitter域名
    for test_url in main_twitter_urls:
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
                success_count += 1
            elif response.status_code in [301, 302, 303, 307, 308]:
                # 重定向也算成功
                logging.info(f"✅ 代理验证成功，{test_url} 返回重定向")
                success_count += 1
            else:
                logging.warning(f"❌ {test_url} 返回状态码: {response.status_code}")
                
        except requests.exceptions.ProxyError:
            logging.warning(f"❌ 代理连接失败: {test_url}")
        except requests.exceptions.Timeout:
            logging.warning(f"❌ 代理访问超时: {test_url}")
        except requests.exceptions.ConnectionError:
            logging.warning(f"❌ 代理连接错误: {test_url}")
        except Exception as e:
            logging.warning(f"❌ 访问 {test_url} 异常: {e}")
    
    # 如果主要URL都成功，直接返回成功
    if success_count == total_main_urls:
        logging.info(f"✅ 所有主要Twitter域名都可以正常访问 ({success_count}/{total_main_urls})")
        return True
    
    # 如果有部分成功，也认为代理可用
    if success_count > 0:
        logging.info(f"✅ 部分Twitter域名可以正常访问 ({success_count}/{total_main_urls})")
        return True
    
    # 如果主要URL都失败，尝试备用URL
    logging.info(f"主要Twitter域名都无法访问，尝试备用URL: {backup_url}")
    try:
        response = requests.get(
            backup_url, 
            proxies=proxy_dict, 
            timeout=5,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            allow_redirects=True
        )
        
        if response.status_code == 200 or response.status_code in [301, 302, 303, 307, 308]:
            logging.info(f"✅ 备用URL验证成功: {backup_url}")
            return True
        else:
            logging.warning(f"❌ 备用URL返回状态码: {response.status_code}")
            
    except Exception as e:
        logging.warning(f"❌ 备用URL访问异常: {e}")
    
    logging.warning("❌ 所有推特URL都无法通过代理访问")
    return False


def verify_direct_twitter_connection() -> bool:
    """
    验证直连（无代理）是否可以访问Twitter
    Returns:
        bool: 直连是否可用
    """
    # 主要的Twitter测试URL
    main_twitter_urls = [
        "https://twitter.com",
        "https://x.com"
    ]
    
    # 备用测试URL
    backup_url = "https://api.twitter.com"
    
    success_count = 0
    total_main_urls = len(main_twitter_urls)
    
    # 测试主要的Twitter域名（直连模式）
    for test_url in main_twitter_urls:
        try:
            logging.info(f"尝试直连访问: {test_url}")
            
            response = requests.get(
                test_url, 
                timeout=5,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                },
                allow_redirects=True
            )
            
            if response.status_code == 200:
                logging.info(f"✅ 直连验证成功，可以正常访问 {test_url}")
                success_count += 1
            elif response.status_code in [301, 302, 303, 307, 308]:
                # 重定向也算成功
                logging.info(f"✅ 直连验证成功，{test_url} 返回重定向")
                success_count += 1
            else:
                logging.warning(f"❌ {test_url} 返回状态码: {response.status_code}")
                
        except requests.exceptions.Timeout:
            logging.warning(f"❌ 直连访问超时: {test_url}")
        except requests.exceptions.ConnectionError:
            logging.warning(f"❌ 直连连接错误: {test_url}")
        except Exception as e:
            logging.warning(f"❌ 直连访问 {test_url} 异常: {e}")
    
    # 如果主要URL都成功，直接返回成功
    if success_count == total_main_urls:
        logging.info(f"✅ 所有主要Twitter域名都可以直连访问 ({success_count}/{total_main_urls})")
        return True
    
    # 如果有部分成功，也认为直连可用
    if success_count > 0:
        logging.info(f"✅ 部分Twitter域名可以直连访问 ({success_count}/{total_main_urls})")
        return True
    
    # 如果主要URL都失败，尝试备用URL
    logging.info(f"主要Twitter域名都无法直连访问，尝试备用URL: {backup_url}")
    try:
        response = requests.get(
            backup_url, 
            timeout=5,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            allow_redirects=True
        )
        
        if response.status_code == 200 or response.status_code in [301, 302, 303, 307, 308]:
            logging.info(f"✅ 备用URL直连验证成功: {backup_url}")
            return True
        else:
            logging.warning(f"❌ 备用URL返回状态码: {response.status_code}")
            
    except Exception as e:
        logging.warning(f"❌ 备用URL直连访问异常: {e}")
    
    logging.warning("❌ 所有推特URL都无法直连访问")
    return False


def setup_proxy() -> Optional[Dict[str, str]]:
    """
    设置代理配置，使用推特验证，包含降级处理
    Returns:
        Dict[str, str] or None: 代理配置字典，失败时返回None
    """
    global _global_proxy, _twitter_accessible
    
    logging.info("🔍 开始检测系统代理...")
    
    # 1. 尝试检测系统代理
    system_proxy = get_system_proxy()
    
    if system_proxy:
        logging.info(f"检测到系统代理: {system_proxy.get('http', 'N/A')}")
        
        # 2. 使用推特验证代理可用性
        if verify_proxy_twitter(system_proxy):
            logging.info("✅ 代理验证成功，可以正常访问推特，所有网络请求将使用代理")
            _global_proxy = system_proxy
            _twitter_accessible = True
            return system_proxy
        else:
            logging.warning("❌ 代理无法访问推特，降级为直连模式")
            logging.info("🔍 尝试直连模式访问推特...")
            
            # 测试直连是否能访问Twitter
            if verify_direct_twitter_connection():
                logging.info("✅ 直连验证成功，可以正常访问推特，使用直连模式")
                _global_proxy = None
                _twitter_accessible = True
                return None
            else:
                logging.warning("❌ 直连也无法访问推特，网络连接可能存在问题")
                logging.info("⚠️ Twitter粉丝数获取功能将被禁用，程序将继续运行其他功能")
                _global_proxy = None
                _twitter_accessible = False
                return None
    else:
        logging.info("未检测到系统代理，测试直连模式访问推特...")
        
        # 3. 测试直连是否能访问Twitter
        if verify_direct_twitter_connection():
            logging.info("✅ 直连验证成功，可以正常访问推特，使用直连模式")
            _global_proxy = None
            _twitter_accessible = True
            return None
        else:
            logging.warning("❌ 直连无法访问推特，建议检查网络连接或配置代理")
            logging.info("⚠️ Twitter粉丝数获取功能将被禁用，程序将继续运行其他功能")
            _global_proxy = None
            _twitter_accessible = False
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
    base_status = ""
    if has_proxy():
        base_status = f"使用代理: {_global_proxy.get('http', 'N/A')}"
    else:
        base_status = "直连模式"
    
    # 添加Twitter可用性信息
    twitter_status = "Twitter可用" if _twitter_accessible else "Twitter不可用"
    return f"{base_status}, {twitter_status}"


def is_twitter_accessible() -> bool:
    """检查Twitter是否可用"""
    return _twitter_accessible


def reset_twitter_accessibility():
    """重置Twitter可用性状态"""
    global _twitter_accessible
    _twitter_accessible = True 