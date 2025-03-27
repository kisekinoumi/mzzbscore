import logging
import sys
import time
from html import unescape

import pandas as pd
from openpyxl import load_workbook

# 导入自定义模块
from models import Anime
from utils import preprocess_name
from utils.logger import setup_logger, date_error
from utils.global_variables import ALLOWED_YEARS, DESIRED_YEAR, FILE_PATH, update_constants
from biz.extractors import (
    extract_bangumi_data,
    extract_myanimelist_data,
    extract_anilist_data,
    extract_filmarks_data
)
from biz.data_process.excel_handler import update_excel_data
import concurrent.futures

# 配置日志
logging = setup_logger()

try:
    # 读取Excel文件
    wb = load_workbook(FILE_PATH)
    ws = wb.active

    # 更新全局常量
    update_constants(str(ws['A1'].value)[:4])  # 读取表格设置目标放送年份

    df = pd.read_excel(FILE_PATH, skiprows=1)
    # 遍历DataFrame中的每一行数据
    for index, row in df.iterrows():
        if pd.isna(row['原名']):
            logging.warning(f"Skipping row {index} because the original name is NaN.")
            continue  # 跳过这一行
        anime = Anime(original_name=row['原名'])  # 获取每行的"原名"列作为原始名称
        logging.info(str(anime))
        # 预处理名称
        processed_name = preprocess_name(anime.original_name)

        # 提取数据 - 并发执行
        # 原始的串行执行代码（注释掉）
        # extract_bangumi_data(anime, processed_name)
        # extract_myanimelist_data(anime, processed_name)
        # extract_anilist_data(anime, processed_name)
        # extract_filmarks_data(anime, processed_name)
        
        # 创建线程池执行器
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # 提交所有任务到线程池
            future_to_extractor = {
                executor.submit(extract_bangumi_data, anime, processed_name): "bangumi",
                executor.submit(extract_myanimelist_data, anime, processed_name): "myanimelist",
                executor.submit(extract_anilist_data, anime, processed_name): "anilist",
                executor.submit(extract_filmarks_data, anime, processed_name): "filmarks"
            }
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(future_to_extractor):
                extractor_name = future_to_extractor[future]
                try:
                    result = future.result()
                    logging.info(f"{extractor_name} extractor completed")
                except Exception as exc:
                    logging.error(f"{extractor_name} extractor generated an exception: {exc}")

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
        wb.save(FILE_PATH)
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