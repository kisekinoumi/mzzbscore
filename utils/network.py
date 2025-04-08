# utils/network.py
# 存放网络请求相关的工具函数

import logging
import time
import requests

# 常量定义
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10  # 设置请求超时时间，单位为秒
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'

# 简单的内存缓存，用于存储请求结果
_request_cache = {}

def fetch_data_with_retry(url, params=None, data=None, method='GET', headers=None, use_cache=True, cache_ttl=300):
    """
    带有重试机制的请求函数。

    Args:
        url (str): 请求的URL。
        params (dict, optional): URL参数。默认为None。
        data (dict, optional): 请求体数据，适用于POST请求。默认为None。
        method (str, optional): 请求方法，'GET' 或 'POST'。默认为 'GET'。
        headers (dict, optional): 请求头。默认为 None。
        use_cache (bool, optional): 是否使用缓存。默认为True。
        cache_ttl (int, optional): 缓存有效期，单位为秒。默认为300秒(5分钟)。

    Returns:
        requests.Response: 请求成功时的响应对象，如果所有重试都失败则返回None。
    """
    # 设置默认请求头
    if headers is None:
        headers = {}
    if 'User-Agent' not in headers:
        headers['User-Agent'] = DEFAULT_USER_AGENT
    
    # 生成缓存键
    cache_key = f"{method}:{url}:{str(params)}:{str(data)}"
    
    # 检查缓存
    if method == 'GET' and use_cache and cache_key in _request_cache:
        cache_entry = _request_cache[cache_key]
        cache_time, cached_response = cache_entry
        # 检查缓存是否过期
        if time.time() - cache_time < cache_ttl:
            logging.debug(f"Using cached response for {url}")
            return cached_response
    
    logging.info(f"Fetching data from {url} with method {method}")
    
    for attempt in range(MAX_RETRIES):
        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=REQUEST_TIMEOUT, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # 处理不同的HTTP状态码
            if response.status_code == 429:  # 请求过多
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait_time = int(retry_after)
                else:
                    # 如果没有 Retry-After 字段，则采用指数退避
                    wait_time = 2 ** attempt * 5
                logging.warning(f"Received 429 Too Many Requests. Waiting for {wait_time} seconds before retrying...")
                time.sleep(wait_time)
                continue
            elif response.status_code >= 500:  # 服务器错误
                wait_time = 2 ** attempt * 5
                logging.warning(f"Received server error {response.status_code}. Waiting for {wait_time} seconds before retrying...")
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            
            # 缓存成功的GET请求结果
            if method == 'GET' and use_cache:
                _request_cache[cache_key] = (time.time(), response)
                
            return response

        except requests.exceptions.Timeout as e:
            # 超时错误，可能需要更长的等待时间
            wait_time = 2 ** attempt * 10
            logging.warning(f"Request timed out for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}. Waiting for {wait_time} seconds.")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
        except requests.exceptions.ConnectionError as e:
            # 连接错误，可能是网络问题
            wait_time = 2 ** attempt * 5
            logging.warning(f"Connection error for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}. Waiting for {wait_time} seconds.")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            # 其他请求错误
            wait_time = 2 ** attempt * 5
            logging.warning(f"Request failed for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}. Waiting for {wait_time} seconds.")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)
            else:
                logging.error(f"Max retries reached for {url}. Giving up.")
                return None
    
    logging.error(f"All attempts failed for {url}.")
    return None