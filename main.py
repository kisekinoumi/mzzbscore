import logging
import sys
import time
from html import unescape

import pandas as pd
from openpyxl import load_workbook

# 导入自定义模块
from models import Anime
from utils import preprocess_name
from biz.extractors import (
    extract_bangumi_data,
    extract_myanimelist_data,
    extract_anilist_data,
    extract_filmarks_data
)
from biz.data_process.excel_handler import update_excel_data

# 配置日志
log_file_path = 'mzzb_score.log'
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path, mode='w', encoding='utf-8'),  # 'w' 覆盖模式
                        logging.StreamHandler(sys.stdout)  # 同时输出到控制台
                    ])

# 常量定义
date_error = []  # 用于存储日期错误信息

# 全局变量，将在程序运行时设置
ALLOWED_YEARS = []
DESIRED_YEAR = ""

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
        anime = Anime(original_name=row['原名'])  # 获取每行的"原名"列作为原始名称
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