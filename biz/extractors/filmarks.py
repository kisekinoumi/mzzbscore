# extractors/filmarks.py
# 存放Filmarks数据提取逻辑

import re
import json
import logging
from urllib.parse import quote
from lxml import html
from utils import fetch_data_with_retry, LinkParser


def extract_filmarks_data(anime, processed_name):
    """
    从Filmarks提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    # 检查是否已有Filmarks URL
    if anime.filmarks_url:
        filmarks_info = LinkParser.extract_filmarks_info(anime.filmarks_url)
        if filmarks_info:
            logging.info(f"使用已有Filmarks链接提取数据: {anime.filmarks_url}")
            return extract_filmarks_data_by_url(anime, filmarks_info['full_url'])
    
    # 如果没有链接，则进行搜索
    logging.info(f"通过搜索获取Filmarks数据: {processed_name}")
    return extract_filmarks_data_by_search(anime, processed_name)


def extract_filmarks_data_by_url(anime, filmarks_url):
    """
    通过URL直接从Filmarks条目页面提取数据
    Args:
        anime: Anime对象
        filmarks_url: Filmarks条目页面URL
    Returns:
        bool: 是否成功提取数据
    """
    filmarks_response = fetch_data_with_retry(filmarks_url)
    
    if not filmarks_response or filmarks_response.status_code != 200:
        logging.error(f"Filmarks条目页面请求失败: {filmarks_url}")
        anime.score_fm = "Request failed"
        return False

    filmarks_tree = html.fromstring(filmarks_response.content)
    anime.filmarks_url = filmarks_url
    
    try:
        # 提取评分
        score_elements = filmarks_tree.xpath('//div[@class="c2-rating-l__text"]/text()')
        if score_elements:
            anime.score_fm = score_elements[0].strip()
        else:
            anime.score_fm = 'No score found'
        
        # 提取名称
        name_elements = filmarks_tree.xpath('//h2[@class="p-content-detail__title"]/span/text()')
        if name_elements:
            anime.filmarks_name = name_elements[0].strip()
        else:
            anime.filmarks_name = 'No name found'
        
        # 提取评分人数 - 从data-mark属性的JSON中提取count字段
        data_mark_elements = filmarks_tree.xpath('//div[@class="js-btn-mark"]/@data-mark')
        if data_mark_elements:
            try:
                data_mark_json = data_mark_elements[0].replace('&quot;', '"')
                data_mark = json.loads(data_mark_json)
                anime.filmarks_total = str(data_mark.get('count', 'No count found'))
            except (json.JSONDecodeError, KeyError):
                anime.filmarks_total = 'No count found'
        else:
            anime.filmarks_total = 'No count found'
        
        # 提取开播日期 - 从公開日信息中提取
        date_elements = filmarks_tree.xpath('//div[@class="p-content-detail__other-info"]//h3[@class="p-content-detail__other-info-title"][contains(text(), "公開日")]/text()')
        if date_elements:
            date_text = date_elements[0].strip()  # 例如 "公開日：2025年01月10日"
            # 从 "公開日：2025年01月10日" 格式中提取年月
            date_match = re.search(r'(\d{4})年(\d{2})月', date_text)
            if date_match:
                year = date_match.group(1)
                month = date_match.group(2)
                anime.filmarks_subject_Date = year + month
                logging.info(f"Filmarks开播日期: {anime.filmarks_subject_Date}")
            else:
                logging.warning(f"Filmarks日期格式不匹配: {date_text}")
        else:
            logging.warning("Filmarks未找到公開日信息")
        
        logging.info(f"Filmarks链接: {anime.filmarks_url}")
        logging.info(f"Filmarks名称: {anime.filmarks_name}")
        logging.info(f"Filmarks评分: {anime.score_fm}")
        logging.info(f"Filmarks评分人数: {anime.filmarks_total}")
        
    except Exception as e:
        logging.error(f"Filmarks条目页面数据提取失败: {e}")
        anime.score_fm = 'No Filmarks score found'
        anime.filmarks_name = 'No name found'
        anime.filmarks_total = 'No count found'
        return False
    
    return True


def extract_filmarks_data_by_search(anime, processed_name):
    """
    通过搜索从Filmarks页面提取动画评分
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    keyword_encoded = quote(processed_name)
    filmarks_url = f"https://filmarks.com/search/animes?q={keyword_encoded}"
    filmarks_response = fetch_data_with_retry(filmarks_url)

    if not filmarks_response or filmarks_response.status_code != 200:
        anime.score_fm = 'No Filmarks results'
        logging.warning("Filmarks搜索请求失败")
        return False

    filmarks_tree = html.fromstring(filmarks_response.content)
    
    try:
        # 首先定位第一个搜索结果容器
        first_result = filmarks_tree.xpath('//div[contains(@class, "js-cassette")][1]')
        
        if not first_result:
            anime.score_fm = 'No search results found'
            anime.filmarks_name = 'No search results found'
            logging.warning("未找到搜索结果")
            return False
        
        first_cassette = first_result[0]
        
        # 在第一个搜索结果中查找评分，使用相对xpath
        anime_fm_score_elements = first_cassette.xpath(
            './/div[@class="c-rating__score"]//text() | '
            './/*[contains(@class, "score")]//text() | '
            './/*[contains(@class, "rating")]//text()'
        )
        
        anime.score_fm = 'No score found'
        if anime_fm_score_elements:
            for score_text in anime_fm_score_elements:
                score_text = score_text.strip()
                # 匹配数字格式的评分（如 4.1, 3.5 等）
                score_match = re.search(r'^(\d+\.?\d*)$', score_text)
                if score_match and score_text != '-':
                    anime.score_fm = score_match.group(1)
                    break

        anime.filmarks_url = filmarks_url  # 存储Filmarks URL

        # 在第一个搜索结果中查找动画名称，使用相对xpath
        filmarks_name_elements = first_cassette.xpath(
            './/h3[@class="p-content-cassette__title"]//text() | '
            './/*[contains(@class, "title") and not(contains(@class, "reviews-title"))]//text()'
        )
        
        anime.filmarks_name = 'No name found'
        if filmarks_name_elements:
            for name_text in filmarks_name_elements:
                clean_name = name_text.strip()
                # 过滤掉太短的文本和无意义的文本
                if clean_name and len(clean_name) > 3 and '検索' not in clean_name:
                    anime.filmarks_name = clean_name
                    break

        # 获取评分人数，在第一个搜索结果中查找
        filmarks_total = first_cassette.xpath('.//@data-mark')
        if filmarks_total:
            data_mark = json.loads(filmarks_total[0])
            anime.filmarks_total = data_mark.get('count', 'No count found')
        else:
            anime.filmarks_total = 'No total found'

        logging.info("Filmarks的链接: " + str(anime.filmarks_url))
        logging.info("Filmarks的名称: " + str(anime.filmarks_name))
        logging.info("Filmarks的评分: " + str(anime.score_fm))
        logging.info("Filmarks的评分人数: " + str(anime.filmarks_total))

        # 在第一个搜索结果中查找日期信息
        filmarks_date_elements = first_cassette.xpath(
            './/*[contains(text(), "年")]//text() | '
            './/*[contains(@class, "date")]//text() | '
            './/*[contains(@class, "other-info")]//text()'
        )
        
        if filmarks_date_elements:
            for date_text in filmarks_date_elements:
                date_str = date_text.strip()
                match = re.search(r'(\d{4})年(\d{2})月', date_str)
                if match:
                    year = match.group(1)
                    month = match.group(2)
                    anime.filmarks_subject_Date = year + month  # "YYYYMM"
                    logging.info("Filmarks开播日期: " + str(anime.filmarks_subject_Date))
                    break
            else:
                logging.info("未找到Filmarks日期信息")
        else:
            logging.info("未获取到Filmarks日期")

    except IndexError:
        anime.score_fm = 'No Filmarks score found'  # 没有找到评分
        logging.warning(anime.score_fm)
    except Exception as e:
        anime.score_fm = 'No Filmarks score found'
        logging.error(f"Filmarks数据提取失败: {e}")
    
    return True