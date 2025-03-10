import logging
import re
import sys
import time
from html import unescape
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
date_error = []  # 用于存储日期错误信息


# Anime 类，并增加更多的属性用于存储不同平台的数据
class Anime:
    def __init__(self, original_name, score_bgm='', score_al='', score_mal='', score_fm='',
                 bangumi_url='', anilist_url='', myanimelist_url='', filmarks_url='',
                 bangumi_name='', anilist_name='', myanimelist_name='', flimarks_name='',
                 bangumi_total='', anilist_total='', myanimelist_total='', filmarks_total='',
                 bangumi_subject_Date='', myanimelist_subject_Date='', anilist_subject_Date='',
                 filmarks_subject_Date=''):
        self.original_name = original_name  # 原始名称
        self.score_bgm = score_bgm  # Bangumi 评分
        self.score_al = score_al  # AniList 评分
        self.score_mal = score_mal  # MyAnimeList 评分
        self.score_fm = score_fm  # Filmarks 评分
        self.bangumi_url = bangumi_url  # Bangumi 条目链接
        self.anilist_url = anilist_url  # AniList 条目链接
        self.myanimelist_url = myanimelist_url  # MyAnimeList 条目链接
        self.filmarks_url = filmarks_url  # Filmarks 条目链接
        self.bangumi_name = bangumi_name  # Bangumi 名称
        self.anilist_name = anilist_name  # AniList 名称
        self.myanimelist_name = myanimelist_name  # MyAnimeList 名称
        self.flimarks_name = flimarks_name  # Filmarks 名称
        self.bangumi_total = bangumi_total  # Bangumi 评分人数
        self.anilist_total = anilist_total  # AniList 人气/评分人数
        self.myanimelist_total = myanimelist_total  # MyAnimeList 评分人数
        self.filmarks_total = filmarks_total  # Filmarks 评分人数
        # 开播日期统一格式为 "YYYYMM"
        self.bangumi_subject_Date = bangumi_subject_Date
        self.myanimelist_subject_Date = myanimelist_subject_Date
        self.anilist_subject_Date = anilist_subject_Date
        self.filmarks_subject_Date = filmarks_subject_Date

    def __str__(self):
        return (f"Anime({self.original_name}, BGM: {self.score_bgm}, AL: {self.score_al}, "
                f"MAL: {self.score_mal}, FM: {self.score_fm}, "
                f"URLs: {self.bangumi_url}, {self.anilist_url}, {self.myanimelist_url}, {self.filmarks_url}, "
                f"Names: {self.bangumi_name}, {self.anilist_name}, {self.myanimelist_name}, {self.flimarks_name}, "
                f"StartDates: BGM:{self.bangumi_subject_Date}, MAL:{self.myanimelist_subject_Date}, "
                f"AL:{self.anilist_subject_Date}, FM:{self.filmarks_subject_Date})")


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

            # 如果遇到 429 错误，检查响应头中的 Retry-After 字段
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait_time = int(retry_after)
                else:
                    # 如果没有 Retry-After 字段，则采用指数退避
                    wait_time = 2 ** attempt * 5
                logging.warning(f"Received 429 Too Many Requests. Waiting for {wait_time} seconds before retrying...")
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logging.warning(f"Request failed for {url} (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt * 5
                time.sleep(wait_time)
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
    """从Bangumi v0 API提取动画评分。（如果放送年份不在 ALLOWED_YEARS 中则选择下一个条目，最多尝试5次）。"""

    search_url = "https://api.bgm.tv/v0/search/subjects"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42'
    }
    # 设置请求体，尝试获取最多 5 个条目
    search_data = {
        "keyword": processed_name,
        "filter": {"type": [2]}
    }
    search_response = fetch_data_with_retry(
        url=search_url,
        method='POST',
        params={"limit": 5},
        data=search_data,
        headers=headers
    )

    if search_response:
        try:
            search_result = search_response.json()
            # 保存返回数据到文件方便调试（可选）
            with open("outporiginal_name.html", "w", encoding="utf-8") as f:
                f.write(search_response.text)
        except requests.exceptions.JSONDecodeError:
            logging.error(f"Error decoding JSON response for {anime.original_name}")
            return False

        if 'data' in search_result and search_result['data']:
            subjects = search_result['data']
            candidate_found = False
            candidate_subject_data = None
            candidate_subject = None
            attempts = 0

            # 遍历候选条目，最多尝试 5 个
            for candidate in subjects:
                attempts += 1
                candidate_id = candidate['id']
                subject_url = f"https://api.bgm.tv/v0/subjects/{candidate_id}"
                subject_response = fetch_data_with_retry(url=subject_url, headers=headers)
                if subject_response:
                    try:
                        candidate_subject_data = subject_response.json()
                    except requests.exceptions.JSONDecodeError:
                        logging.error(f"Error decoding JSON for candidate subject {candidate_id}")
                        continue

                    # 判断候选数据中是否有 "date" 字段且格式为 YYYY-MM-DD
                    if "date" in candidate_subject_data and isinstance(candidate_subject_data["date"], str):
                        bgm_subject_cname = candidate.get('name_cn', 'No name found')
                        date_str = candidate_subject_data["date"]
                        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                            year = date_str[:4]
                            # 使用全局变量 ALLOWED_YEARS 判断年份是否符合要求
                            if year in ALLOWED_YEARS:
                                candidate_found = True
                                candidate_subject = candidate
                                anime.bangumi_subject_Date = year + date_str[5:7]  # 转换为 "YYYYMM"
                                logging.info(
                                    f"选中条目名称{bgm_subject_cname},选中候选条目 {candidate_id}，放送日期: {anime.bangumi_subject_Date}")
                                break
                            else:
                                logging.info(
                                    f"选中条目名称{bgm_subject_cname},候选条目 {candidate_id} 的放送年份 {year} 不符合要求。")
                        else:
                            logging.info(
                                f"选中条目名称{bgm_subject_cname},候选条目 {candidate_id} 的放送日期格式不正确: {date_str}")
                    else:
                        logging.info(f"候选条目 {candidate_id} 缺少 'date' 字段。")
                else:
                    logging.warning(f"候选条目 {candidate_id} 的详情请求失败。")
                if attempts >= 5:
                    break

            if not candidate_found:
                logging.error("尝试5次后，没有找到放送年份在 {} 的候选条目。".format("/".join(ALLOWED_YEARS)))
                anime.score_bgm = "No acceptable subject found"
                return False

            # 使用选中的候选条目继续处理
            first_subject_id = candidate_subject['id']
            anime.bangumi_url = f"https://bgm.tv/subject/{first_subject_id}"
            anime.bangumi_name = candidate_subject.get('name', 'No name found')
            logging.info("选中Bangumi链接: " + str(anime.bangumi_url))
            logging.info("选中Bangumi名称: " + str(anime.bangumi_name))

            # 处理评分信息
            if ('rating' in candidate_subject_data and
                    'count' in candidate_subject_data['rating'] and
                    candidate_subject_data['rating']['count']):
                total = candidate_subject_data['rating']['total']
                score_counts = candidate_subject_data['rating']['count']
                weighted_sum = sum(int(score) * int(count) for score, count in score_counts.items())
                calculated_score = round(weighted_sum / total, 2)
                anime.score_bgm = f"{calculated_score:.2f}"
                anime.bangumi_total = str(total)
                logging.info("Bangumi页面评分: " + str(candidate_subject_data['rating'].get('score')))
                logging.info("Bangumi评分: " + str(anime.score_bgm))
                logging.info("Bangumi评分人数: " + str(anime.bangumi_total))
            else:
                anime.score_bgm = 'No score available'
                logging.warning("选中条目无评分信息。")
        else:
            anime.score_bgm = 'No results found'
            logging.warning("Bangumi无结果")
    else:
        anime.score_bgm = 'Request failed'
        logging.warning("Bangumi请求失败")
    return True


def extract_myanimelist_data(anime, processed_name):
    """从MyAnimeList页面提取动画评分。"""
    keyword_encoded = quote(processed_name)
    mal_search_url = f"https://myanimelist.net/anime.php?q={keyword_encoded}&cat=anime"
    mal_search_response = fetch_data_with_retry(mal_search_url)
    if mal_search_response and mal_search_response.status_code == 200:
        mal_tree = html.fromstring(mal_search_response.content)
        # 获取候选条目（假设表格中的每一行代表一个候选；具体XPath可能需要根据页面结构调整）
        candidate_elements = mal_tree.xpath(
            "//table[@border='0' and @cellpadding='0' and @cellspacing='0' and @width='100%']/tr")
        candidate_found = False
        candidate_data = None
        attempts = 0
        for candidate in candidate_elements[1:]:  # 跳过标题行
            attempts += 1
            if attempts > 5:
                break
            try:
                anime_href_element = candidate.xpath(".//div[1]/a[1]")[0]
            except IndexError:
                continue
            candidate_href = anime_href_element.get('href')
            # 请求候选条目的页面
            mal_candidate_response = fetch_data_with_retry(candidate_href)
            if mal_candidate_response:
                candidate_html = mal_candidate_response.text
                # 提取临时名称
                myanimelist_temp_name_match = re.search(r'<h1 class="title-name h1_bold_none"><strong>(.*?)</strong>',
                                                        candidate_html)
                myanimelist_temp_name = str(
                    myanimelist_temp_name_match.group(1).strip()) if myanimelist_temp_name_match else None
                # 提取 Aired 部分（格式如 "Jan 10, 2025 to ?"）
                air_date_match = re.search(r'<span class="dark_text">Aired:</span>\s*(?:<td>)?([^<]+)', candidate_html)
                if air_date_match:
                    air_date_str = air_date_match.group(1).strip()
                    # 用正则提取月份英文缩写和年份
                    match = re.search(r'([A-Za-z]{3})\s+\d{1,2},\s+(\d{4})', air_date_str)
                    if match:
                        candidate_year = match.group(2)
                        if candidate_year in ALLOWED_YEARS:
                            candidate_found = True
                            candidate_data = {
                                "href": candidate_href,
                                "html": candidate_html
                            }
                            # 记录 MAL 的放送日期，统一格式为 "YYYYMM"
                            month_abbr = match.group(1)
                            month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                                         "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                                         "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
                            candidate_month = month_map.get(month_abbr, "00")
                            anime.myanimelist_subject_Date = candidate_year + candidate_month
                            logging.info(
                                f"选中MAL候选条目名称为 {myanimelist_temp_name},选中MAL候选条目 {candidate_href}，放送日期: {anime.myanimelist_subject_Date}")
                            break
                        else:
                            logging.info(
                                f"选中MAL候选条目名称为 {myanimelist_temp_name},MAL候选条目的放送年份 {candidate_year} 不符合要求。")
                    else:
                        logging.info(
                            f"选中MAL候选条目名称为 {myanimelist_temp_name},MAL候选条目的日期格式不匹配: " + air_date_str)
                else:
                    logging.info(f"选中MAL候选条目名称为 {myanimelist_temp_name},MAL候选条目没有找到 Aired 日期。")
            else:
                logging.warning(f"MAL候选条目 {candidate_href} 页面请求失败。")
        if not candidate_found:
            logging.error("尝试5次后，没有找到放送年份符合要求的 MAL 候选条目。")
            anime.score_mal = "No acceptable subject found"
            return False
        # 使用选中的候选条目继续处理
        html_content = candidate_data["html"]
        anime.myanimelist_url = candidate_data["href"]
        # 提取评分信息
        anime_mal_score_match = re.search(r'<span itemprop="ratingValue" class="score-label score-\d+">([\d.]+)',
                                          html_content)
        anime.score_mal = str(anime_mal_score_match.group(1)) if anime_mal_score_match else None
        # 提取名称
        myanimelist_name_match = re.search(r'<h1 class="title-name h1_bold_none"><strong>(.*?)</strong>', html_content)
        anime.myanimelist_name = str(myanimelist_name_match.group(1).strip()) if myanimelist_name_match else None
        mal_match = re.search(r'<span itemprop="ratingCount" style="display: none">(\d+)', html_content)
        anime.myanimelist_total = str(mal_match.group(1)) if mal_match else 'No score found'
        logging.info("MAL链接: " + str(anime.myanimelist_url))
        logging.info("MAL名称: " + str(anime.myanimelist_name))
        logging.info("MAL评分: " + str(anime.score_mal))
        logging.info("MAL评分人数: " + str(anime.myanimelist_total))
    else:
        anime.score_mal = 'No results found'
        logging.warning(anime.score_mal)
    return True


def extract_anilist_data(anime, processed_name):
    """从AniList API提取动画评。"""
    anilist_url = 'https://graphql.anilist.co'
    anilist_search_query = '''
    query ($search: String) {
      Page (page: 1, perPage: 5) {
        media (search: $search, type: ANIME) {
          id
          title {
            romaji
          }
          startDate {
            year
            month
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
                candidate_found = False
                candidate_media = None
                attempts = 0
                for candidate in media_list:
                    attempts += 1
                    if attempts > 5:
                        break
                    anilist_temp_name = candidate['title']['romaji']
                    start_date = candidate.get('startDate', {})
                    candidate_year = str(start_date.get('year')) if start_date.get('year') else None
                    if candidate_year and candidate_year in ALLOWED_YEARS:
                        candidate_found = True
                        candidate_media = candidate
                        candidate_month = start_date.get('month')
                        if candidate_month:
                            anime.anilist_subject_Date = f"{candidate_year}{candidate_month:02d}"
                        else:
                            anime.anilist_subject_Date = candidate_year
                        logging.info(
                            f"选中AniList候选条目名称为{anilist_temp_name},选中AniList候选条目 {candidate['id']}，放送日期: {anime.anilist_subject_Date}")
                        break
                    else:
                        logging.info(
                            f"选中AniList候选条目名称为{anilist_temp_name},AniList候选条目的放送年份 {candidate_year} 不符合要求。")
                if not candidate_found:
                    logging.error("尝试5次后，没有找到放送年份符合要求的 AniList 候选条目。")
                    anime.score_al = "No acceptable subject found"
                    return False
                # 使用选中的候选条目继续处理
                first_anime_id = candidate_media['id']
                anime.anilist_url = f"https://anilist.co/anime/{first_anime_id}"
                anime.anilist_name = candidate_media['title']['romaji']
                # 使用单独查询获取评分和人气数据
                anilist_detail_query = '''
                query ($id: Int) {
                  Media (id: $id) {
                    averageScore
                    popularity
                  }
                }
                '''
                anilist_detail_variables = {"id": first_anime_id}
                anilist_detail_response = fetch_data_with_retry(anilist_url, method='POST',
                                                                data={'query': anilist_detail_query,
                                                                      'variables': anilist_detail_variables})
                if anilist_detail_response:
                    anilist_detail_data = anilist_detail_response.json()
                    if 'data' in anilist_detail_data and 'Media' in anilist_detail_data['data']:
                        anime_detail = anilist_detail_data['data']['Media']
                        anime.score_al = anime_detail.get('averageScore', 'No score found')
                        anime.anilist_total = str(anime_detail.get('popularity', 'No popularity info'))
                        logging.info("AniList链接: " + str(anime.anilist_url))
                        logging.info("AniList名称: " + str(anime.anilist_name))
                        logging.info("AniList评分: " + str(anime.score_al))
                        logging.info("AniList评分人数: " + str(anime.anilist_total))
                        logging.info("AniList开播日期: " + str(anime.anilist_subject_Date))
                    else:
                        anime.score_al = 'No AniList results'
                        logging.warning("无AniList数据")
                else:
                    anime.score_al = 'No response results'
                    logging.warning("AniList请求失败")
            else:
                anime.score_al = 'No AniList results'
                anime.popularity = 'No popularity info'
                logging.warning("AniList无结果")

        else:
            logging.warning("Error with AniList API")
            anime.score_al = 'Error with AniList API'  # API请求出错
    else:
        anime.score_al = 'Request failed'
        logging.warning("AniList请求失败")
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

            filmarks_date = filmarks_tree.xpath(
                '/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[2]/div[2]/span[1]/text()'
            )
            if filmarks_date:
                date_str = filmarks_date[0].strip()  # 例如 "2025年01月02日"
                match = re.search(r'(\d{4})年(\d{2})月', date_str)
                if match:
                    year = match.group(1)
                    month = match.group(2)
                    anime.filmarks_subject_Date = year + month  # "YYYYMM"
                    logging.info("Filmarks开播日期: " + str(anime.filmarks_subject_Date))
                else:
                    logging.info("Filmarks日期格式不匹配")
            else:
                logging.info("未获取到Filmarks日期")

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
    current_row = ws[index + 3]  # DataFrame是从0开始的，而Excel是从1开始的，且第一行通常是表头
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
                f"{al_score / 10:.1f}" if (is_valid_value(anime.score_al) and al_score is not None) else None)
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

        # ---------------------放送日期写入---------------------
        try:
            error_cell = ws.cell(row=index + 2, column=18)

            # 检查哪些平台的日期数据缺失
            missing_platforms = []
            if not anime.bangumi_subject_Date:
                missing_platforms.append("bangumi")
            if not anime.myanimelist_subject_Date:
                missing_platforms.append("myanimelist")
            if not anime.anilist_subject_Date:
                missing_platforms.append("anilist")
            if not anime.filmarks_subject_Date:
                missing_platforms.append("filmarks")

            error_message = ""
            # 如果有缺失的平台
            if missing_platforms:
                missing_msg = "/".join(missing_platforms) + "放送日期不存在"
                logging.info(missing_msg)
                error_message = missing_msg
                error_cell.value = missing_msg

                # 获取有日期数据的平台及其值
                valid_dates = {}
                if anime.bangumi_subject_Date:
                    valid_dates["Bangumi"] = anime.bangumi_subject_Date
                if anime.myanimelist_subject_Date:
                    valid_dates["MAL"] = anime.myanimelist_subject_Date
                if anime.anilist_subject_Date:
                    valid_dates["AniList"] = anime.anilist_subject_Date
                if anime.filmarks_subject_Date:
                    valid_dates["Filmarks"] = anime.filmarks_subject_Date

                # 判断剩余的日期是否一致
                if len(valid_dates) > 1:
                    dates = list(valid_dates.values())
                    all_same = all(date == dates[0] for date in dates)

                    if not all_same:
                        diff_str = "; ".join([f"{platform}: {date}" for platform, date in valid_dates.items()])
                        logging.info("存在的平台放送日期不相同: " + diff_str)
                        error_message += "; " + diff_str
                        error_cell.value += "; " + diff_str
            else:
                # 所有平台都有日期数据，判断是否一致
                if (anime.bangumi_subject_Date == anime.myanimelist_subject_Date ==
                        anime.anilist_subject_Date == anime.filmarks_subject_Date):
                    logging.info("四个平台的开播日期相同: " + anime.bangumi_subject_Date)
                    error_cell.value = ""
                    error_message = ""
                else:
                    diff_str = (f"Bangumi: {anime.bangumi_subject_Date}; "
                                f"AniList: {anime.anilist_subject_Date}; "
                                f"MAL: {anime.myanimelist_subject_Date}; "
                                f"Filmarks: {anime.filmarks_subject_Date}")
                    logging.info("四个平台的开播日期不相同: " + diff_str)
                    error_cell.value = diff_str
                    error_message = diff_str

            # 如果有错误信息，则添加到date_error列表
            if error_message:
                date_error.append({
                    "name": anime.original_name,
                    "error": error_message
                })

        except Exception as e:
            logging.error(f"在处理索引 {index} 时发生错误: {e}")
            pass

try:
    # 读取Excel文件，假设文件名为mzzb.xlsx
    file_path = 'mzzb.xlsx'
    wb = load_workbook(file_path)
    ws = wb.active

    DESIRED_YEAR = str(ws['A1'].value)[:4]  # 读取表格设置目标放送年份
    ALLOWED_YEARS = [DESIRED_YEAR, str(int(DESIRED_YEAR) - 1)]  # 例如 ["2025", "2024"]

    df = pd.read_excel(file_path, skiprows=1)
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

        # 如果 MAL 没有找到候选条目，但 AniList 搜到名称，则用 AniList 返回的名称重新搜索 MAL
        if anime.score_mal == "No acceptable subject found" and anime.anilist_name:
            logging.info("MAL候选未找到，尝试使用 AniList 返回的名称重新搜索 MAL")
            new_processed_name = preprocess_name(anime.anilist_name)
            extract_myanimelist_data(anime, new_processed_name)
        # 如果 AniList 没有找到候选条目，但 MAL 搜到名称，则用 MAL 返回的名称重新搜索 AniList
        if anime.score_al == "No acceptable subject found" and anime.myanimelist_name:
            logging.info("AniList候选未找到，尝试使用 MAL 返回的名称重新搜索 AniList")
            new_processed_name = unescape(preprocess_name(anime.myanimelist_name))
            extract_anilist_data(anime, new_processed_name)


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

        # 输出日期错误信息
        if date_error:
            logging.info("\n" + "=" * 50)
            logging.info("日期错误汇总 (共 %d 条):" % len(date_error))
            logging.info("=" * 50)
            for i, error in enumerate(date_error, 1):
                logging.info("%d. 作品：%s" % (i, error["name"]))
                logging.info("   错误：%s" % error["error"])
                logging.info("-" * 50)
        else:
            logging.info("没有发现任何日期错误！")
    except Exception as e:
        logging.error(f"保存Excel文件时发生错误: {e}")
    while True:
        user_input = input("输入 'exit' 退出程序: ")
        if user_input.lower() == 'exit':  # 忽略大小写，允许 'exit' 退出
            break
    logging.info("程序已退出...")