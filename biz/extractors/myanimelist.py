# extractors/myanimelist.py
# 存放MyAnimeList数据提取逻辑

import re
import logging
from urllib.parse import quote
from lxml import html
from utils import fetch_data_with_retry, LinkParser


def extract_myanimelist_data(anime, processed_name):
    """
    从MyAnimeList提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    # 检查是否已有MyAnimeList URL
    if anime.myanimelist_url:
        candidate_href = LinkParser.extract_myanimelist_url(anime.myanimelist_url)
        if candidate_href:
            logging.info(f"使用已有MyAnimeList链接提取数据: {anime.myanimelist_url}")
            return extract_myanimelist_data_by_url(anime, candidate_href)
    
    # 如果没有链接，则进行搜索
    logging.info(f"通过搜索获取MyAnimeList数据: {processed_name}")
    return extract_myanimelist_data_by_search(anime, processed_name)


def extract_myanimelist_data_by_url(anime, candidate_href):
    """
    通过URL直接从MyAnimeList提取数据
    Args:
        anime: Anime对象
        candidate_href: MyAnimeList页面URL
    Returns:
        bool: 是否成功提取数据
    """
    # 请求候选条目的页面
    mal_candidate_response = fetch_data_with_retry(candidate_href)
    if not mal_candidate_response:
        logging.error(f"MyAnimeList页面请求失败: {candidate_href}")
        anime.score_mal = "Request failed"
        return False

    html_content = mal_candidate_response.text
    
    # 设置基本信息
    anime.myanimelist_url = candidate_href
    
    # 提取名称
    myanimelist_name_match = re.search(r'<h1 class="title-name h1_bold_none"><strong>(.*?)</strong>', html_content)
    anime.myanimelist_name = str(myanimelist_name_match.group(1).strip()) if myanimelist_name_match else 'No name found'
    
    # 提取 Aired 部分（格式如 "Jan 10, 2025 to ?"）
    air_date_match = re.search(r'<span class="dark_text">Aired:</span>\s*(?:<td>)?([^<]+)', html_content)
    if air_date_match:
        air_date_str = air_date_match.group(1).strip()
        # 用正则提取月份英文缩写和年份
        match = re.search(r'([A-Za-z]{3})\s+\d{1,2},\s+(\d{4})', air_date_str)
        if match:
            year = match.group(2)
            month_abbr = match.group(1)
            month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                         "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                         "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
            month = month_map.get(month_abbr, "00")
            anime.myanimelist_subject_Date = year + month
            logging.info(f"MyAnimeList开播日期: {anime.myanimelist_subject_Date}")
        else:
            logging.warning(f"MyAnimeList日期格式不匹配: {air_date_str}")
    else:
        logging.warning("MyAnimeList未找到Aired日期")
    
    # 提取评分信息
    anime_mal_score_match = re.search(r'<span itemprop="ratingValue" class="score-label score-\d+">([\d.]+)', html_content)
    anime.score_mal = str(anime_mal_score_match.group(1)) if anime_mal_score_match else 'No score found'
    
    # 提取评分人数
    mal_match = re.search(r'<span itemprop="ratingCount" style="display: none">(\d+)', html_content)
    anime.myanimelist_total = str(mal_match.group(1)) if mal_match else 'No score found'
    
    logging.info(f"MyAnimeList链接: {anime.myanimelist_url}")
    logging.info(f"MyAnimeList名称: {anime.myanimelist_name}")
    logging.info(f"MyAnimeList评分: {anime.score_mal}")
    logging.info(f"MyAnimeList评分人数: {anime.myanimelist_total}")
    return True


def extract_myanimelist_data_by_search(anime, processed_name):
    """
    通过搜索从MyAnimeList页面提取动画评分
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    # 导入全局变量
    from utils.global_variables import ALLOWED_YEARS
    
    keyword_encoded = quote(processed_name)
    mal_search_url = f"https://myanimelist.net/anime.php?q={keyword_encoded}&cat=anime"
    mal_search_response = fetch_data_with_retry(mal_search_url)
    
    if not mal_search_response or mal_search_response.status_code != 200:
        anime.score_mal = 'No results found'
        logging.warning("MyAnimeList搜索请求失败")
        return False

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
        if not mal_candidate_response:
            logging.warning(f"MyAnimeList候选条目 {candidate_href} 页面请求失败")
            continue

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
                    logging.info(f"选中MAL候选条目名称为 {myanimelist_temp_name},选中MAL候选条目 {candidate_href}，放送日期: {anime.myanimelist_subject_Date}")
                    break
                else:
                    logging.info(f"选中MAL候选条目名称为 {myanimelist_temp_name},MAL候选条目的放送年份 {candidate_year} 不符合要求")
            else:
                logging.info(f"选中MAL候选条目名称为 {myanimelist_temp_name},MAL候选条目的日期格式不匹配: {air_date_str}")
        else:
            logging.info(f"选中MAL候选条目名称为 {myanimelist_temp_name},MAL候选条目没有找到 Aired 日期")
    
    if not candidate_found:
        logging.error("尝试5次后，没有找到放送年份符合要求的 MAL 候选条目")
        anime.score_mal = "No acceptable subject found"
        return False
    
    # 使用选中的候选条目继续处理
    html_content = candidate_data["html"]
    anime.myanimelist_url = candidate_data["href"]
    
    # 提取评分信息
    anime_mal_score_match = re.search(r'<span itemprop="ratingValue" class="score-label score-\d+">([\d.]+)',
                                      html_content)
    anime.score_mal = str(anime_mal_score_match.group(1)) if anime_mal_score_match else 'No score found'
    
    # 提取名称
    myanimelist_name_match = re.search(r'<h1 class="title-name h1_bold_none"><strong>(.*?)</strong>', html_content)
    anime.myanimelist_name = str(myanimelist_name_match.group(1).strip()) if myanimelist_name_match else 'No name found'
    
    mal_match = re.search(r'<span itemprop="ratingCount" style="display: none">(\d+)', html_content)
    anime.myanimelist_total = str(mal_match.group(1)) if mal_match else 'No score found'
    
    logging.info(f"MyAnimeList链接: {anime.myanimelist_url}")
    logging.info(f"MyAnimeList名称: {anime.myanimelist_name}")
    logging.info(f"MyAnimeList评分: {anime.score_mal}")
    logging.info(f"MyAnimeList评分人数: {anime.myanimelist_total}")
    return True