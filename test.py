import requests
import pandas as pd
import requests
from lxml import html
from openpyxl import load_workbook
import time
import sys
import re

# 指定要获取的URL
url = "https://myanimelist.net/search/all?q=%E5%9C%B0%E7%B8%9B%E5%B0%91%E5%B9%B4%E8%8A%B1%E5%AD%90%E3%81%8F%E3%82%932&cat=anime"
mal_search_response = requests.get(url)
if mal_search_response.status_code == 200:
    mal_tree = html.fromstring(mal_search_response.content)
    # 获取搜索结果中第一个条目的链接
    anime_href_element = mal_tree.xpath('/html/body/div[1]/div[2]/div[4]/div[2]/div[2]/div[1]/div/article[1]/div[1]/div[2]/div[1]/a[1]')[0]
    anime_href = anime_href_element.get('href')
    print(html.tostring(anime_href_element, pretty_print=True, encoding="unicode"))
    print(anime_href)
