import logging
import re
import sys
import time
from urllib.parse import quote  # 明确引入quote函数

import pandas as pd
import requests
from lxml import html
from openpyxl import load_workbook

# 配置日志
log_file_path = 'mzzb_score.log'
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path, mode='w', encoding='utf-8'),  # 'w' 覆盖模式
                        logging.StreamHandler(sys.stdout)  # 同时输出到控制台
                    ])

# 常量定义
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10  # 设置请求超时时间，单位为秒


# Anime 类，并增加更多的属性用于存储不同平台的数据
class Anime:
    def __init__(self, original_name, score_bgm='', score_al='', score_mal='', score_fm='',
                 bangumi_url='', anilist_url='', myanimelist_url='', filmarks_url='',
                 bangumi_name='', anilist_name='', myanimelist_name='', flimarks_name='', bangumi_total='',
                 anilist_total='', myanimelist_total='', filmarks_total=''):
        self.original_name = original_name  # 原始名称
        self.score_bgm = score_bgm  # Bangumi评分
        self.score_al = score_al  # AniList评分
        self.score_mal = score_mal  # MyAnimeList评分
        self.score_fm = score_fm  # Filmarks评分
        self.bangumi_url = bangumi_url  # Bangumi条目链接
        self.anilist_url = anilist_url  # AniList条目链接
        self.myanimelist_url = myanimelist_url  # MyAnimeList条目链接
        self.filmarks_url = filmarks_url  # Filmarks条目链接
        self.bangumi_name = bangumi_name  # Bangumi名称
        self.anilist_name = anilist_name  # AniList名称
        self.myanimelist_name = myanimelist_name  # MyAnimeList名称
        self.flimarks_name = flimarks_name  # Filmarks名称
        self.bangumi_total = bangumi_total  # Bangumi评分人数
        self.anilist_total = anilist_total  # AniList评分人数
        self.myanimelist_total = myanimelist_total  # MyAnimeList评分人数
        self.filmarks_total = filmarks_total  # Filmarks评分人数

    def __str__(self):
        return (f"Anime({self.original_name}, BGM: {self.score_bgm}, AL: {self.score_al}, "
                f"MAL: {self.score_mal}, FM: {self.score_fm}, "
                f"URLs: {self.bangumi_url}, {self.anilist_url}, {self.myanimelist_url}, {self.filmarks_url}, "
                f"Names: {self.bangumi_name}, {self.anilist_name}, {self.myanimelist_name}, {self.flimarks_name})")


def fetch_data_with_retry(url, params=None, data=None, method='GET', headers=None):
    """
    带有重试机制的请求函数。

    Args:
        url (str): 请求的URL。
        params (dict, optional): URL参数。默认为None。\
        data (dict, optional): 请求体数据，适用于POST请求。默认为None。
        method (str, optional): 请求方法，'GET' 或 'POST'。默认为 'GET'。
        headers (dict, optional): 请求头。默认为 None。

    Returns:
        requests.Response: 请求成功时的响应对象，如果所有重试都失败则返回None。
    """
    for attempt in range(MAX_RETRIES):
        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=REQUEST_TIMEOUT, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()  # 检查HTTP状态码，非200会抛出异常
            return response

        except requests.exceptions.RequestException as e:
            logging.warning(f"Request failed for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # 指数退避
            else:
                logging.error(f"Max retries reached for {url}. Giving up.")
                return None
    return None


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


def extract_bangumi_data(anime, processed_name):
    """从Bangumi v0 API提取动画评分。"""
    # 使用v0 API的正确搜索接口
    search_url = "https://api.bgm.tv/v0/search/subjects"

    # 设置v0 API所需的请求头
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42'
    }

    # 构建请求体 - POST 请求
    search_data = {
        "keyword": processed_name,
        "filter": {
            "type": [2]  # 2表示动画类型
        }
    }

    # 使用 POST 方法并传递 JSON 请求体
    search_response = fetch_data_with_retry(
        url=search_url,
        method='POST',
        params={"limit": 1},  # 只需要第一个结果
        data=search_data,
        headers=headers
    )

    if search_response:
        try:
            search_result = search_response.json()
        except requests.exceptions.JSONDecodeError:
            logging.error(f"Error decoding JSON response for {anime.original_name}")
            return False

        if 'data' in search_result and search_result['data']:
            first_subject = search_result['data'][0]
            first_subject_id = first_subject['id']  # 获取第一个条目的ID
            anime.bangumi_url = f"https://bgm.tv/subject/{first_subject_id}"  # 构造Bangumi条目URL
            anime.bangumi_name = first_subject.get('name', 'No name found')  # 获取Bangumi名称

            logging.info("bgm的链接:" + str(anime.bangumi_url))
            logging.info("bgm的条目名字:" + str(anime.bangumi_name))

            # 使用v0 API获取条目详情
            subject_url = f"https://api.bgm.tv/v0/subjects/{first_subject_id}"
            subject_response = fetch_data_with_retry(url=subject_url, headers=headers)

            if subject_response:
                try:
                    subject_data = subject_response.json()

                    if 'rating' in subject_data and 'count' in subject_data['rating'] and subject_data['rating'][
                        'count']:
                        total = subject_data['rating']['total']
                        score_counts = subject_data['rating']['count']
                        # 确保score和count都是整数类型
                        weighted_sum = sum(int(score) * int(count) for score, count in score_counts.items())
                        calculated_score = round(weighted_sum / total, 2)
                        anime.score_bgm = f"{calculated_score:.2f}"  # 保存评分
                        anime.bangumi_total = str(total)

                        logging.info('bgm的页面评分' + str(subject_data['rating']['score']))
                        logging.info("bgm的评分:" + str(anime.score_bgm))
                        logging.info("bgm的评分人数:" + str(anime.bangumi_total))
                    else:
                        anime.score_bgm = 'No score available'
                        logging.warning("No rating information found for Bangumi data.")
                except requests.exceptions.JSONDecodeError:
                    anime.score_bgm = 'No score available'
                    logging.error(f"Error decoding JSON response for subject {first_subject_id}")
            else:
                anime.score_bgm = 'No score available'
                logging.warning("No subject_response information found for Bangumi data.")
        else:
            anime.score_bgm = 'No results found'  # 没有搜索到结果
    else:
        anime.score_bgm = 'Request failed'

    return True


def extract_myanimelist_data(anime, processed_name):
    """从MyAnimeList页面提取动画评分。"""
    keyword_encoded = quote(processed_name)
    mal_search_url = f"https://myanimelist.net/anime.php?q={keyword_encoded}&cat=anime"
    mal_search_response = fetch_data_with_retry(mal_search_url)

    if mal_search_response and mal_search_response.status_code == 200:
        mal_tree = html.fromstring(mal_search_response.content)
        try:
            # 获取搜索结果中第一个条目的链接
            anime_href_element = mal_tree.xpath(
                "//table[@border='0' and @cellpadding='0' and @cellspacing='0' and @width='100%']/tr[2]/td[1]/div[1]/a[1]")[
                0]
            anime_href = anime_href_element.get('href')
            anime.myanimelist_url = anime_href  # 存储MyAnimeList条目链接
            mal_anime_response = fetch_data_with_retry(anime_href)

            if mal_anime_response:
                mal_html_content = mal_anime_response.text
                anime_mal_score_match = re.search(
                    r'<span itemprop="ratingValue" class="score-label score-\d+">([\d.]+)', mal_html_content)
                anime.score_mal = str(anime_mal_score_match.group(1)) if anime_mal_score_match else None

                myanimelist_name_match = re.search(r'<h1 class="title-name h1_bold_none"><strong>(.*?)</strong>',
                                                   mal_html_content)
                anime.myanimelist_name = str(
                    myanimelist_name_match.group(1).strip()) if myanimelist_name_match else None

                mal_match = re.search(r'<span itemprop="ratingCount" style="display: none">(\d+)', mal_html_content)
                anime.myanimelist_total = str(mal_match.group(1)) if mal_match else 'No score found'
                logging.info("MAL的链接: " + str(anime.myanimelist_url))
                logging.info("MAL的名称: " + str(anime.myanimelist_name))
                logging.info("MAL的评分: " + str(anime.score_mal))
                logging.info("MAL的评分人数: " + str(anime.myanimelist_total))
            else:
                anime.score_mal = 'No score found'

        except IndexError:
            anime.score_mal = 'No href found'  # 没有找到条目链接
            logging.warning(anime.score_mal)
    else:
        anime.score_mal = 'No results found'  # 请求失败
        logging.warning(anime.score_mal)
    return True


def extract_anilist_data(anime, processed_name):
    """从AniList API提取动画评。"""
    anilist_url = 'https://graphql.anilist.co'
    anilist_search_query = '''
    query ($search: String) {
      Page (page: 1, perPage: 1) {
        media (search: $search, type: ANIME) {
          id
          title {
            romaji
          }
        }
      }
    }
    '''
    anilist_search_variables = {
        "search": processed_name  # 使用原始名称进行搜索
    }

    anilist_search_response = fetch_data_with_retry(anilist_url, method='POST', data={'query': anilist_search_query,
                                                                                      'variables': anilist_search_variables})

    if anilist_search_response:
        anilist_search_data = anilist_search_response.json()

        if 'data' in anilist_search_data and 'Page' in anilist_search_data['data']:
            media_list = anilist_search_data['data']['Page']['media']
            if media_list:
                first_anime_id = media_list[0]['id']  # 获取第一个条目的ID
                anime.anilist_url = f"https://anilist.co/anime/{first_anime_id}"  # 构造AniList条目URL
                anime.anilist_name = media_list[0]['title']['romaji']  # 获取AniList名称

                anilist_detail_query = '''
                query ($id: Int) {
                  Media (id: $id) {
                    averageScore
                    popularity
                  }
                }
                '''
                anilist_detail_variables = {
                    "id": first_anime_id
                }
                anilist_detail_response = fetch_data_with_retry(anilist_url, method='POST',
                                                                data={'query': anilist_detail_query,
                                                                      'variables': anilist_detail_variables})

                if anilist_detail_response:
                    anilist_detail_data = anilist_detail_response.json()

                    if 'data' in anilist_detail_data and 'Media' in anilist_detail_data['data']:
                        anime_detail = anilist_detail_data['data']['Media']
                        anime.score_al = anime_detail.get('averageScore', 'No score found')
                        anime.anilist_total = str(anime_detail.get('popularity', 'No popularity info'))
                        logging.info("AniList的链接: " + str(anime.anilist_url))
                        logging.info("AniList的名称: " + str(anime.anilist_name))
                        logging.info("AniList的评分: " + str(anime.score_al))
                        logging.info("AniList的评分人数: " + str(anime.anilist_total))
                    else:
                        anime.score_al = 'No AniList results'
                else:
                    anime.score_al = 'No response results'
            else:
                anime.score_al = 'No AniList results'
                anime.popularity = 'No popularity info'

        else:
            logging.warning("Error with AniList API")
            anime.score_al = 'Error with AniList API'  # API请求出错
    else:
        anime.score_al = 'Request failed'
    return True


def extract_filmarks_data(anime, processed_name):
    """从Filmarks页面提取动画评分。"""
    keyword_encoded = quote(processed_name)
    filmarks_url = f"https://filmarks.com/search/animes?q={keyword_encoded}"
    filmarks_response = fetch_data_with_retry(filmarks_url)

    if filmarks_response and filmarks_response.status_code == 200:
        filmarks_tree = html.fromstring(filmarks_response.content)
        try:
            anime_fm_score = filmarks_tree.xpath(
                '/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[2]/div[3]/div/div[2]/text()')
            anime.score_fm = anime_fm_score[0].strip() if anime_fm_score else 'No score found'
            anime.filmarks_url = filmarks_url  # 存储Filmarks URL

            filmarks_name = filmarks_tree.xpath(
                '/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[2]/div[1]/h3/text()')
            anime.flimarks_name = filmarks_name[0].strip() if filmarks_name else 'No name found'

            filmarks_total = filmarks_tree.xpath(
                '/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[1]/div[2]/div[1]/a/span/text()')
            anime.filmarks_total = filmarks_total[0].strip() if filmarks_total else 'No name found'

            logging.info("Filmarks的链接: " + str(anime.filmarks_url))
            logging.info("Filmarks的名称: " + str(anime.flimarks_name))
            logging.info("Filmarks的评分: " + str(anime.score_fm))
            logging.info("Filmarks的评分人数: " + str(anime.filmarks_total))

        except IndexError:
            anime.score_fm = 'No Filmarks score found'  # 没有找到评分
            logging.warning(anime.score_fm)
    else:
        anime.score_fm = 'No Filmarks results'  # Filmarks请求失败
    return True


def update_excel_data(ws, index, anime):
    """
    更新Excel表格中的数据，每次写入单元格时都进行try-except，
    以防止单个操作出错导致整个程序停止。
    """
    current_row = ws[index + 2]  # DataFrame是从0开始的，而Excel是从1开始的，且第一行通常是表头
    if current_row[0].value == anime.original_name:  # 匹配原始名称

        # 定义不可用值
        unavailable_values = [
            'No score available', 'No results found', '', None,
            'No href found', 'No Filmarks score found', 'No Filmarks results',
            'N/A', 'No score found', 'No AniList results',
            'Error with AniList API', 'No response results'
        ]

        # 辅助函数，用于安全地将值转换为float，如果无法转换则返回None。
        def safe_float(value):
            """安全地将值转换为float，如果无法转换则返回None。"""
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        # 辅助函数，用于判断值是否有效
        def is_valid_value(value):
            return value not in unavailable_values

        # 辅助函数，用于安全地将数据写入Excel单元格
        def write_value(cell, value):
            """将值安全地写入Excel单元格，处理None值。"""
            cell.value = value if value is not None else None

        # ---------------------Bangumi数据写入---------------------
        bgm_score = safe_float(anime.score_bgm)
        bgm_total = safe_float(anime.bangumi_total)
        try:
            write_value(current_row[2], bgm_score if is_valid_value(anime.score_bgm) else None)
        except Exception as e:
            logging.error(f"Error writing Bangumi score for {anime.original_name[:50]}: {e}")
        try:
            write_value(current_row[3], bgm_total if is_valid_value(anime.bangumi_total) else None)
        except Exception as e:
            logging.error(f"Error writing Bangumi total for {anime.original_name[:50]}: {e}")

        # ---------------------AniList数据写入---------------------
        al_score = safe_float(anime.score_al)
        al_total = safe_float(anime.anilist_total)
        # AniList评分通常是满100，所以这里做除以10的处理
        try:
            write_value(
                current_row[4],
                al_score / 10 if (is_valid_value(anime.score_al) and al_score is not None) else None
            )
        except Exception as e:
            logging.error(f"Error writing AniList score for {anime.original_name[:50]}: {e}")
        try:
            write_value(
                current_row[5],
                al_total if is_valid_value(anime.anilist_total) else None
            )
        except Exception as e:
            logging.error(f"Error writing AniList total for {anime.original_name[:50]}: {e}")

        # ---------------------MyAnimeList数据写入---------------------
        mal_score = safe_float(anime.score_mal)
        mal_total = safe_float(anime.myanimelist_total)
        try:
            write_value(
                current_row[6],
                mal_score if is_valid_value(anime.score_mal) else None
            )
        except Exception as e:
            logging.error(f"Error writing MAL score for {anime.original_name[:50]}: {e}")
        try:
            write_value(
                current_row[7],
                mal_total if is_valid_value(anime.myanimelist_total) else None
            )
        except Exception as e:
            logging.error(f"Error writing MAL total for {anime.original_name[:50]}: {e}")

        # ---------------------Filmarks数据写入---------------------
        fm_score = safe_float(anime.score_fm)
        try:
            write_value(
                current_row[8],
                fm_score if is_valid_value(anime.score_fm) else None
            )
        except Exception as e:
            logging.error(f"Error writing Filmarks score for {anime.original_name[:50]}: {e}")
        try:
            write_value(
                current_row[9],
                fm_score * 2 if is_valid_value(anime.score_fm) and fm_score is not None else None
            )
        except Exception as e:
            logging.error(f"Error writing Filmarks “乘2”分数 for {anime.original_name[:50]}: {e}")
        try:
            write_value(
                current_row[10],
                anime.filmarks_total if is_valid_value(anime.filmarks_total) else None
            )
        except Exception as e:
            logging.error(f"Error writing Filmarks total for {anime.original_name[:50]}: {e}")

        # ---------------------Bangumi 链接、名称写入---------------------
        try:
            write_value(
                current_row[13],
                anime.bangumi_name if anime.bangumi_name not in ['No name found', None] else None
            )
        except Exception as e:
            logging.error(f"Error writing Bangumi name for {anime.original_name[:50]}: {e}")
        try:
            if anime.bangumi_url:
                ws.cell(row=index + 2, column=14).hyperlink = anime.bangumi_url
        except Exception as e:
            logging.error(f"Error writing Bangumi URL for {anime.original_name[:50]}: {e}")

        # ---------------------AniList 链接、名称写入---------------------
        try:
            write_value(
                current_row[14],
                anime.anilist_name if anime.anilist_name not in ['No name found', None] else None
            )
        except Exception as e:
            logging.error(f"Error writing AniList name for {anime.original_name[:50]}: {e}")
        try:
            if anime.anilist_url:
                ws.cell(row=index + 2, column=15).hyperlink = anime.anilist_url
        except Exception as e:
            logging.error(f"Error writing AniList URL for {anime.original_name[:50]}: {e}")

        # ---------------------MyAnimeList 链接、名称写入---------------------
        try:
            write_value(
                current_row[15],
                anime.myanimelist_name if anime.myanimelist_name not in ['No name found', None] else None
            )
        except Exception as e:
            logging.error(f"Error writing MAL name for {anime.original_name[:50]}: {e}")
        try:
            if anime.myanimelist_url:
                ws.cell(row=index + 2, column=16).hyperlink = anime.myanimelist_url
        except Exception as e:
            logging.error(f"Error writing MAL URL for {anime.original_name[:50]}: {e}")

        # ---------------------Filmarks 链接、名称写入---------------------
        try:
            write_value(
                current_row[16],
                anime.flimarks_name if anime.flimarks_name not in ['No name found', None] else None
            )
        except Exception as e:
            logging.error(f"Error writing Filmarks name for {anime.original_name[:50]}: {e}")
        try:
            if anime.filmarks_url:
                ws.cell(row=index + 2, column=17).hyperlink = anime.filmarks_url
        except Exception as e:
            logging.error(f"Error writing Filmarks URL for {anime.original_name[:50]}: {e}")


try:
    # 读取Excel文件，假设文件名为test.xlsx
    file_path = 'mzzb.xlsx'
    wb = load_workbook(file_path)
    ws = wb.active
    df = pd.read_excel(file_path)

    # 遍历DataFrame中的每一行数据
    for index, row in df.iterrows():
        if pd.isna(row['原名']):
            logging.warning(f"Skipping row {index} because the original name is NaN.")
            continue  # 跳过这一行
        anime = Anime(original_name=row['原名'])  # 获取每行的“原名”列作为原始名称
        logging.info(str(anime))
        # 预处理名称
        processed_name = preprocess_name(anime.original_name)

        # 提取数据
        extract_bangumi_data(anime, processed_name)
        extract_myanimelist_data(anime, processed_name)
        extract_anilist_data(anime, processed_name)
        extract_filmarks_data(anime, processed_name)
        # 更新Excel数据
        update_excel_data(ws, index, anime)

        # 延时以避免频繁请求被拒绝
        time.sleep(0.1)

    # # 保存更新后的Excel文件
    # wb.save(file_path)
    # print("Excel表格已成功更新。")

except Exception as e:
    logging.error(f"发生错误: {e}")

finally:
    try:
        wb.save(file_path)
        logging.info("Excel表格已成功更新。")
    except Exception as e:
        logging.error(f"保存Excel文件时发生错误: {e}")
    while True:
        user_input = input("输入 'exit' 退出程序: ")
        if user_input.lower() == 'exit':  # 忽略大小写，允许 'exit' 退出
            break
    logging.info("程序已退出...")