# src/data_process/excel_handler.py
# 存放Excel处理相关的逻辑

import logging
import math

from src.data_process.date_validator import DateValidator
from src.data_process.score_transformers import ScoreTransformer, TotalCountTransformer
from src.extractors.twitter import TwitterFollowersHelper
from utils import (
    ColumnMappings,
    ExcelColumnHelper,
    ExcelColumns,
    TwitterParser,
    is_valid_name,
    safe_float,
)

SCORE_NUMBER_FORMATS = {
    ExcelColumns.BANGUMI_SCORE: "0.00",
    ExcelColumns.ANILIST_SCORE: "0.0",
    ExcelColumns.MYANIMELIST_SCORE: "0.00",
    ExcelColumns.FILMARKS_ORIGINAL_SCORE: "0.0",
    ExcelColumns.FILMARKS_SCORE: "0.0",
}


def update_excel_data(ws, index, anime, col_helper=None):
    """
    更新Excel表格中的数据，使用列名定位和模块化的数据处理。
    每次写入单元格时都进行try-except，以防止单个操作出错导致整个程序停止。
    """
    if col_helper is None:
        col_helper = ExcelColumnHelper(ws)

    row_num = index + 3
    current_row = ws[row_num]

    if current_row[0].value != anime.original_name:
        logging.warning(f"行 {row_num} 的原始名称不匹配，跳过更新")
        return

    # 仅在 "译名" 单元格为空时自动填入 Bangumi 中文名（已有内容绝不覆盖）
    _write_translated_name_if_empty(col_helper, current_row, anime)

    transformed_scores = ScoreTransformer.get_transformed_scores(anime)
    transformed_totals = TotalCountTransformer.get_transformed_totals(anime)

    # ---------------------检查评分人数并设置NaN---------------------
    MIN_TOTAL_COUNT = 50

    if transformed_totals["bangumi"] is not None and transformed_totals["bangumi"] < MIN_TOTAL_COUNT:
        logging.info(f"Bangumi评分人数({transformed_totals['bangumi']})小于{MIN_TOTAL_COUNT}，设置为NaN")
        transformed_scores["bangumi"] = "NaN"
        transformed_totals["bangumi"] = "NaN"

    if transformed_totals["anilist"] is not None and transformed_totals["anilist"] < MIN_TOTAL_COUNT:
        logging.info(f"AniList评分人数({transformed_totals['anilist']})小于{MIN_TOTAL_COUNT}，设置为NaN")
        transformed_scores["anilist"] = "NaN"
        transformed_totals["anilist"] = "NaN"

    if (
        transformed_totals["myanimelist"] is not None
        and transformed_totals["myanimelist"] < MIN_TOTAL_COUNT
    ):
        logging.info(
            f"MyAnimeList评分人数({transformed_totals['myanimelist']})小于{MIN_TOTAL_COUNT}，设置为NaN"
        )
        transformed_scores["myanimelist"] = "NaN"
        transformed_totals["myanimelist"] = "NaN"

    if transformed_totals["filmarks"] is not None and transformed_totals["filmarks"] < MIN_TOTAL_COUNT:
        logging.info(f"Filmarks评分人数({transformed_totals['filmarks']})小于{MIN_TOTAL_COUNT}，设置为NaN")
        transformed_scores["filmarks"] = "NaN"
        transformed_scores["filmarks_doubled"] = "NaN"
        transformed_totals["filmarks"] = "NaN"

    # ---------------------各平台数据写入---------------------
    platform_key_mapping = {
        "Bangumi": "bangumi",
        "AniList": "anilist",
        "MyAnimeList": "myanimelist",
        "Filmarks": "filmarks",
    }

    for platform_name, mapping in ColumnMappings.SCORE_MAPPINGS.items():
        platform_key = platform_key_mapping[platform_name]

        if platform_name == "Filmarks":
            # 兼容不含 "Filmarks原始评分" 列的首月/完结评分模板
            data_mapping = {
                "doubled_score": (mapping["doubled_score"], transformed_scores["filmarks_doubled"]),
                "total": (mapping["total"], transformed_totals[platform_key]),
            }
            if col_helper.has_column(mapping["original_score"]):
                data_mapping["original_score"] = (
                    mapping["original_score"],
                    transformed_scores[platform_key],
                )
        else:
            data_mapping = {
                "score": (mapping["score"], transformed_scores[platform_key]),
                "total": (mapping["total"], transformed_totals[platform_key]),
            }

        _write_platform_data(col_helper, current_row, anime, platform_name, data_mapping)

    # ---------------------平台链接、名称写入---------------------
    _write_platform_links_and_names(col_helper, row_num, anime, ColumnMappings.PLATFORM_URL_MAPPINGS)

    # ---------------------Twitter/X 社交媒体写入---------------------
    _write_social_media_data(col_helper, row_num, anime)

    # ---------------------放送日期处理---------------------
    _process_release_date_validation(col_helper, row_num, anime)


def _write_translated_name_if_empty(col_helper, current_row, anime):
    """仅当Excel行的'译名'单元格为空时，自动填入Bangumi返回的中文名，绝不覆盖用户已有内容"""
    cn_name = getattr(anime, "bangumi_chinese_name", "")
    if not is_valid_name(cn_name):
        return

    col_idx = col_helper.get_col_index(ExcelColumns.TRANSLATED_NAME)
    if col_idx is None:
        return

    try:
        existing_val = current_row[col_idx].value
        if existing_val is not None and str(existing_val).strip() != "":
            return
        if col_helper.safe_write(current_row, ExcelColumns.TRANSLATED_NAME, str(cn_name).strip()):
            logging.info(f"已自动填入译名: {cn_name}")
    except Exception as e:
        logging.warning(f"写入译名列时出错: {e}")


def _write_platform_data(col_helper, current_row, anime, platform_name, data_mapping):
    for field_name, (column_name, value) in data_mapping.items():
        success = _write_platform_value(col_helper, current_row, column_name, value)
        if not success:
            logging.error(f"Error writing {platform_name} {field_name} for {anime.original_name[:50]}")


def _write_platform_value(col_helper, current_row, column_name, value):
    """写入平台字段；指定评分列写入为数值并设置Excel显示格式。"""
    number_format = SCORE_NUMBER_FORMATS.get(column_name)
    if not number_format:
        return col_helper.safe_write(current_row, column_name, value)

    numeric_value = safe_float(value)
    if numeric_value is None or not math.isfinite(numeric_value):
        return col_helper.safe_write(current_row, column_name, value)

    col_idx = col_helper.get_col_index(column_name)
    if col_idx is None:
        logging.warning(f"列 '{column_name}' 不存在，跳过写入")
        return False

    try:
        cell = current_row[col_idx]
        cell.value = numeric_value
        cell.number_format = number_format
        return True
    except Exception as e:
        logging.error(f"写入列 '{column_name}' 时出错: {e}")
        return False


def _write_platform_links_and_names(col_helper, row_num, anime, platform_mapping):
    for platform, mapping in platform_mapping.items():
        name_value = getattr(anime, mapping["name_attr"], None)
        url_value = getattr(anime, mapping["url_attr"], None)

        if is_valid_name(name_value) and url_value:
            success = col_helper.safe_write_hyperlink(row_num, mapping["url_col"], url_value, name_value)
            if success:
                logging.info(f"已写入{platform}超链接: {name_value} -> {url_value}")
            else:
                logging.error(f"Error writing {platform} hyperlink for {anime.original_name[:50]}")
        elif url_value:
            success = col_helper.safe_write(col_helper.ws[row_num], mapping["url_col"], url_value)
            if not success:
                logging.error(f"Error writing {platform} URL for {anime.original_name[:50]}")
        elif is_valid_name(name_value):
            success = col_helper.safe_write(col_helper.ws[row_num], mapping["url_col"], name_value)
            if not success:
                logging.error(f"Error writing {platform} name for {anime.original_name[:50]}")


def _write_social_media_data(col_helper, row_num, anime):
    if anime.twitter_username and anime.twitter_url:
        if TwitterParser.validate_twitter_data(anime.twitter_username, anime.twitter_url):
            display_text = TwitterParser.format_twitter_info_for_display(
                anime.twitter_username, anime.twitter_url
            )
            success = col_helper.safe_write_hyperlink(
                row_num, ExcelColumns.X_TWITTER, anime.twitter_url, display_text
            )
            if success:
                logging.info(f"已写入Twitter超链接: {display_text} -> {anime.twitter_url}")
            else:
                logging.error(f"写入Twitter超链接失败: {anime.original_name[:50]}")
        else:
            logging.warning(
                f"Twitter数据验证失败，跳过写入: @{anime.twitter_username} ({anime.twitter_url})"
            )
    else:
        logging.debug("没有找到有效的Twitter信息")

    if hasattr(anime, "twitter_followers") and anime.twitter_followers:
        try:
            from utils.core.twitter_config import get_twitter_config

            twitter_config = get_twitter_config()
            if twitter_config.is_enabled():
                formatted_followers = TwitterFollowersHelper.format_followers_count(
                    anime.twitter_followers
                )
                success = col_helper.safe_write(
                    col_helper.ws[row_num], ExcelColumns.X_FAN, formatted_followers
                )
                if success:
                    logging.info(f"已写入Twitter粉丝数: {formatted_followers}")
                else:
                    logging.error(f"写入Twitter粉丝数失败: {anime.original_name[:50]}")
            else:
                logging.debug("Twitter功能已禁用，跳过写入粉丝数")
        except Exception as e:
            logging.error(f"写入Twitter粉丝数时出错: {e}")
    else:
        logging.debug("没有找到Twitter粉丝数信息")


def _process_release_date_validation(col_helper, row_num, anime):
    try:
        DateValidator.log_date_validation_result(anime)
        error_message = DateValidator.generate_date_error_message(anime)

        success = col_helper.safe_write(col_helper.ws[row_num], ExcelColumns.DATE_ERROR, error_message)
        if not success:
            try:
                col_helper.ws.cell(row=row_num, column=18).value = error_message
            except Exception as e:
                logging.error(f"无法写入日期错误信息: {e}")

        if DateValidator.should_add_to_error_list(anime):
            error_entry = DateValidator.create_date_error_entry(anime)
            if error_entry:
                from utils import date_error

                date_error.append(error_entry)

    except Exception as e:
        logging.error(f"处理日期验证时发生错误: {e}")
