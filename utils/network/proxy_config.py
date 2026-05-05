# utils/network/proxy_config_temp.py
# 临时版代理配置模块：在原有 Windows 代理检测基础上，增加环境变量与 macOS 系统代理检测。

try:
    import winreg
except ImportError:
    winreg = None

import logging
import os
import subprocess
import sys
from typing import Optional, Dict

import requests


# 全局代理配置
_global_proxy = None

# Twitter可用性状态
_twitter_accessible = True


def _get_env_value(*names: str) -> Optional[str]:
    """按顺序读取环境变量，返回第一个非空值。"""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _normalize_proxy_url(proxy_url: str, default_scheme: str = "http") -> Optional[str]:
    """
    标准化代理 URL。

    支持:
    - 127.0.0.1:7890 -> http://127.0.0.1:7890
    - http://127.0.0.1:7890
    - socks5://127.0.0.1:7890
    """
    if not proxy_url:
        return None

    proxy_url = proxy_url.strip().strip('"').strip("'")
    if not proxy_url:
        return None

    if "://" not in proxy_url:
        proxy_url = f"{default_scheme}://{proxy_url}"

    return proxy_url


def _complete_proxy_dict(proxy_dict: Dict[str, Optional[str]]) -> Optional[Dict[str, str]]:
    """补齐 requests 需要的 http/https 代理字段。"""
    cleaned = {
        key: value
        for key, value in proxy_dict.items()
        if key in ("http", "https") and value
    }

    if "http" not in cleaned and "https" in cleaned:
        cleaned["http"] = cleaned["https"]
    elif "https" not in cleaned and "http" in cleaned:
        cleaned["https"] = cleaned["http"]

    return cleaned or None


def _single_proxy_dict(proxy_url: str, default_scheme: str = "http") -> Optional[Dict[str, str]]:
    """将单个代理地址转换为 requests proxies 字典。"""
    normalized = _normalize_proxy_url(proxy_url, default_scheme=default_scheme)
    if not normalized:
        return None
    return {"http": normalized, "https": normalized}


def _request_get(url: str, *, proxies=None, timeout=5, headers=None, allow_redirects=True):
    """
    执行 GET 请求。

    trust_env=False 可以避免 requests 自动读取 HTTP_PROXY/HTTPS_PROXY，
    从而保证“显式代理验证”和“直连验证”语义明确。
    """
    with requests.Session() as session:
        session.trust_env = False
        return session.get(
            url,
            proxies=proxies,
            timeout=timeout,
            headers=headers,
            allow_redirects=allow_redirects,
        )


def get_env_proxy() -> Optional[Dict[str, str]]:
    """
    从环境变量读取代理配置。

    优先级:
    1. MZZB_PROXY / mzzb_proxy: 项目专用手动代理，设置后同时用于 http/https
    2. HTTPS_PROXY / HTTP_PROXY / ALL_PROXY 及其小写形式
    """
    manual_proxy = _get_env_value("MZZB_PROXY", "mzzb_proxy")
    if manual_proxy:
        proxy_dict = _single_proxy_dict(manual_proxy)
        if proxy_dict:
            logging.info(f"检测到 MZZB_PROXY 手动代理: {proxy_dict.get('http')}")
            return proxy_dict

    http_proxy = _get_env_value("HTTP_PROXY", "http_proxy")
    https_proxy = _get_env_value("HTTPS_PROXY", "https_proxy")
    all_proxy = _get_env_value("ALL_PROXY", "all_proxy")

    if not http_proxy and not https_proxy and all_proxy:
        proxy_dict = _single_proxy_dict(all_proxy)
        if proxy_dict:
            logging.info(f"检测到 ALL_PROXY 环境变量代理: {proxy_dict.get('http')}")
            return proxy_dict

    proxy_dict = _complete_proxy_dict({
        "http": _normalize_proxy_url(http_proxy) if http_proxy else None,
        "https": _normalize_proxy_url(https_proxy) if https_proxy else None,
    })

    if proxy_dict:
        logging.info(f"检测到环境变量代理: {proxy_dict.get('http')}")
        return proxy_dict

    return None


def get_windows_proxy() -> Optional[Dict[str, str]]:
    """
    自动检测 Windows 系统代理设置。
    Returns:
        Dict[str, str] or None: 代理配置字典，失败时返回None
    """
    if winreg is None:
        logging.info("当前非Windows系统，跳过Windows系统代理检测")
        return None

    try:
        reg_key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        )

        try:
            proxy_enable, _ = winreg.QueryValueEx(reg_key, "ProxyEnable")
            if not proxy_enable:
                logging.info("Windows系统代理未启用")
                return None

            proxy_server, _ = winreg.QueryValueEx(reg_key, "ProxyServer")
            if not proxy_server:
                return None

            if "=" in proxy_server:
                proxy_dict = {}
                socks_proxy = None

                # 格式: http=127.0.0.1:7890;https=127.0.0.1:7890;socks=127.0.0.1:7891
                for item in proxy_server.split(";"):
                    if "=" not in item:
                        continue
                    protocol, address = item.split("=", 1)
                    protocol = protocol.strip().lower()
                    address = address.strip()

                    if protocol in ("http", "https"):
                        proxy_dict[protocol] = _normalize_proxy_url(address, default_scheme="http")
                    elif protocol in ("socks", "socks5"):
                        socks_proxy = _normalize_proxy_url(address, default_scheme="socks5h")

                completed = _complete_proxy_dict(proxy_dict)
                if completed:
                    return completed

                if socks_proxy:
                    logging.info("检测到Windows SOCKS代理，requests可能需要安装 PySocks 才能使用")
                    return {"http": socks_proxy, "https": socks_proxy}

                return None

            # 格式: 127.0.0.1:7890
            return _single_proxy_dict(proxy_server)

        finally:
            winreg.CloseKey(reg_key)

    except FileNotFoundError:
        logging.info("未找到Windows系统代理设置")
        return None
    except Exception as e:
        logging.warning(f"读取Windows系统代理设置失败: {e}")
        return None


def _parse_scutil_proxy_output(output: str) -> Dict[str, str]:
    """解析 macOS `scutil --proxy` 输出。"""
    result = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def _is_enabled(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes")


def _host_port_proxy(host: Optional[str], port: Optional[str], scheme: str = "http") -> Optional[str]:
    if not host or not port:
        return None
    host = str(host).strip()
    port = str(port).strip()
    if not host or not port:
        return None
    return _normalize_proxy_url(f"{host}:{port}", default_scheme=scheme)


def get_macos_proxy() -> Optional[Dict[str, str]]:
    """
    自动检测 macOS 系统代理设置。

    使用 `scutil --proxy` 读取当前网络服务的静态 HTTP/HTTPS/SOCKS 代理。
    注意：TUN/透明代理模式可能不会出现在 scutil 输出中。
    """
    try:
        result = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        logging.info("当前系统未找到 scutil，跳过macOS系统代理检测")
        return None
    except Exception as e:
        logging.warning(f"读取macOS系统代理设置失败: {e}")
        return None

    if result.returncode != 0:
        logging.warning(f"读取macOS系统代理设置失败，scutil退出码: {result.returncode}")
        return None

    values = _parse_scutil_proxy_output(result.stdout)

    proxy_dict = {}
    if _is_enabled(values.get("HTTPEnable")):
        proxy_dict["http"] = _host_port_proxy(
            values.get("HTTPProxy"),
            values.get("HTTPPort"),
            scheme="http",
        )

    if _is_enabled(values.get("HTTPSEnable")):
        # macOS 的 HTTPSProxy 通常也是 HTTP CONNECT 代理，所以 URL scheme 用 http://。
        proxy_dict["https"] = _host_port_proxy(
            values.get("HTTPSProxy"),
            values.get("HTTPSPort"),
            scheme="http",
        )

    completed = _complete_proxy_dict(proxy_dict)
    if completed:
        logging.info(f"检测到macOS系统代理: {completed.get('http')}")
        return completed

    if _is_enabled(values.get("SOCKSEnable")):
        socks_proxy = _host_port_proxy(
            values.get("SOCKSProxy"),
            values.get("SOCKSPort"),
            scheme="socks5h",
        )
        if socks_proxy:
            logging.info("检测到macOS SOCKS代理，requests可能需要安装 PySocks 才能使用")
            return {"http": socks_proxy, "https": socks_proxy}

    if _is_enabled(values.get("ProxyAutoConfigEnable")):
        logging.info("检测到macOS PAC自动代理配置，但当前临时版本不解析PAC脚本")

    logging.info("macOS系统代理未启用或未检测到静态HTTP/HTTPS代理")
    return None


def get_system_proxy() -> Optional[Dict[str, str]]:
    """
    自动检测系统代理设置。

    检测顺序:
    1. 环境变量 / MZZB_PROXY
    2. Windows 注册表代理
    3. macOS scutil 系统代理
    """
    env_proxy = get_env_proxy()
    if env_proxy:
        return env_proxy

    if sys.platform == "win32":
        return get_windows_proxy()

    if sys.platform == "darwin":
        return get_macos_proxy()

    logging.info("当前非Windows/macOS系统，且未检测到环境变量代理，跳过系统代理自动检测")
    return None


def verify_proxy_twitter(proxy_dict: Dict[str, str]) -> bool:
    """
    验证代理是否可用 - 通过请求推特验证
    Args:
        proxy_dict: 代理配置字典
    Returns:
        bool: 代理是否可用
    """
    main_twitter_urls = [
        "https://twitter.com",
        "https://x.com"
    ]

    backup_url = "https://google.com"

    success_count = 0
    total_main_urls = len(main_twitter_urls)

    for test_url in main_twitter_urls:
        try:
            logging.info(f"尝试通过代理访问: {test_url}")

            response = _request_get(
                test_url,
                proxies=proxy_dict,
                timeout=5,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                },
                allow_redirects=True
            )

            if response.status_code == 200:
                logging.info(f"✅ 代理验证成功，可以正常访问 {test_url}")
                success_count += 1
            elif response.status_code in [301, 302, 303, 307, 308]:
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

    if success_count == total_main_urls:
        logging.info(f"✅ 所有主要Twitter域名都可以正常访问 ({success_count}/{total_main_urls})")
        return True

    if success_count > 0:
        logging.info(f"✅ 部分Twitter域名可以正常访问 ({success_count}/{total_main_urls})")
        return True

    logging.info(f"主要Twitter域名都无法访问，尝试备用URL: {backup_url}")
    try:
        response = _request_get(
            backup_url,
            proxies=proxy_dict,
            timeout=5,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                              '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
    验证直连（无代理）是否可以访问Twitter。

    这里强制 trust_env=False，避免被 HTTP_PROXY/HTTPS_PROXY 影响。
    """
    main_twitter_urls = [
        "https://twitter.com",
        "https://x.com"
    ]

    backup_url = "https://api.twitter.com"

    success_count = 0
    total_main_urls = len(main_twitter_urls)

    for test_url in main_twitter_urls:
        try:
            logging.info(f"尝试直连访问: {test_url}")

            response = _request_get(
                test_url,
                proxies=None,
                timeout=5,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                },
                allow_redirects=True
            )

            if response.status_code == 200:
                logging.info(f"✅ 直连验证成功，可以正常访问 {test_url}")
                success_count += 1
            elif response.status_code in [301, 302, 303, 307, 308]:
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

    if success_count == total_main_urls:
        logging.info(f"✅ 所有主要Twitter域名都可以直连访问 ({success_count}/{total_main_urls})")
        return True

    if success_count > 0:
        logging.info(f"✅ 部分Twitter域名可以直连访问 ({success_count}/{total_main_urls})")
        return True

    logging.info(f"主要Twitter域名都无法直连访问，尝试备用URL: {backup_url}")
    try:
        response = _request_get(
            backup_url,
            proxies=None,
            timeout=5,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                              '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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

    system_proxy = get_system_proxy()

    if system_proxy:
        logging.info(f"检测到系统代理: {system_proxy.get('http', 'N/A')}")

        if verify_proxy_twitter(system_proxy):
            logging.info("✅ 代理验证成功，可以正常访问推特，所有网络请求将使用代理")
            _global_proxy = system_proxy
            _twitter_accessible = True
            return system_proxy
        else:
            logging.warning("❌ 代理无法访问推特，降级为直连模式")
            logging.info("🔍 尝试直连模式访问推特...")

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
    if has_proxy():
        base_status = f"使用代理: {_global_proxy.get('http', 'N/A')}"
    else:
        base_status = "直连模式"

    twitter_status = "Twitter可用" if _twitter_accessible else "Twitter不可用"
    return f"{base_status}, {twitter_status}"


def is_twitter_accessible() -> bool:
    """检查Twitter是否可用"""
    return _twitter_accessible


def reset_twitter_accessibility():
    """重置Twitter可用性状态"""
    global _twitter_accessible
    _twitter_accessible = True
