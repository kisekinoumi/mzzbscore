# extractors/filmarks.py
# 存放Filmarks数据提取逻辑

import re
import json
import logging
from urllib.parse import quote
from lxml import html
from utils import fetch_data_with_retry

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
            anime.filmarks_name = filmarks_name[0].strip() if filmarks_name else 'No name found'

            filmarks_total = filmarks_tree.xpath('//*[@class="js-cassette"]/@data-mark')
            if filmarks_total:
                data_mark = json.loads(filmarks_total[0])
                anime.filmarks_total = data_mark.get('count', 'No count found')
            else:
                anime.filmarks_total = 'No total found'

            logging.info("Filmarks的链接: " + str(anime.filmarks_url))
            logging.info("Filmarks的名称: " + str(anime.filmarks_name))
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