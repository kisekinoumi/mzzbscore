# excel_handler.py
# 存放Excel处理相关的逻辑

import logging
from utils import ExcelColumnHelper, is_valid_value, is_valid_name, ColumnMappings, ExcelColumns, TwitterParser
from src.data_process.score_transformers import ScoreTransformer, TotalCountTransformer
from src.data_process.date_validator import DateValidator

def update_excel_data(ws, index, anime, col_helper=None):
    """
    更新Excel表格中的数据，使用列名定位和模块化的数据处理。
    每次写入单元格时都进行try-except，以防止单个操作出错导致整个程序停止。
    
    Args:
        ws: Excel工作表对象
        index: 行索引
        anime: 动画对象
        col_helper: Excel列助手，如果为None则创建新实例
    """
    # 如果没有传入列助手，则创建新实例
    if col_helper is None:
        col_helper = ExcelColumnHelper(ws)
    
    # 计算实际行号（DataFrame从0开始，Excel从1开始，且有表头）
    row_num = index + 3
    current_row = ws[row_num]
    
    # 匹配原始名称
    if current_row[0].value != anime.original_name:
        logging.warning(f"行 {row_num} 的原始名称不匹配，跳过更新")
        return
    
    # 获取转换后的评分和人数
    transformed_scores = ScoreTransformer.get_transformed_scores(anime)
    transformed_totals = TotalCountTransformer.get_transformed_totals(anime)

    # ---------------------各平台数据写入---------------------
    # 平台名称映射
    platform_key_mapping = {
        "Bangumi": "bangumi",
        "AniList": "anilist", 
        "MyAnimeList": "myanimelist",
        "Filmarks": "filmarks"
    }
    
    for platform_name, mapping in ColumnMappings.SCORE_MAPPINGS.items():
        platform_key = platform_key_mapping[platform_name]
        
        if platform_name == "Filmarks":
            data_mapping = {
                "original_score": (mapping["original_score"], transformed_scores[platform_key]),
                "doubled_score": (mapping["doubled_score"], transformed_scores['filmarks_doubled']),
                "total": (mapping["total"], transformed_totals[platform_key])
            }
        else:
            data_mapping = {
                "score": (mapping["score"], transformed_scores[platform_key]),
                "total": (mapping["total"], transformed_totals[platform_key])
            }
        
        _write_platform_data(col_helper, current_row, anime, platform_name, data_mapping)

    # ---------------------平台链接、名称写入---------------------
    _write_platform_links_and_names(col_helper, row_num, anime, ColumnMappings.PLATFORM_URL_MAPPINGS)

    # ---------------------Twitter/X 社交媒体写入---------------------
    _write_social_media_data(col_helper, row_num, anime)

    # ---------------------放送日期处理---------------------
    _process_release_date_validation(col_helper, row_num, anime)


def _write_platform_data(col_helper, current_row, anime, platform_name, data_mapping):
    """
    写入平台数据的通用函数
    Args:
        col_helper: Excel列助手
        current_row: 当前行
        anime: 动画对象
        platform_name: 平台名称（用于日志）
        data_mapping: 数据映射字典，格式为 {"field_name": ("column_name", value)}
    """
    for field_name, (column_name, value) in data_mapping.items():
        success = col_helper.safe_write(current_row, column_name, value)
        if not success:
            logging.error(f"Error writing {platform_name} {field_name} for {anime.original_name[:50]}")


def _write_platform_links_and_names(col_helper, row_num, anime, platform_mapping):
    """
    写入平台链接和名称的通用函数（超链接形式：显示条目名称，点击跳转到对应链接）
    Args:
        col_helper: Excel列助手
        row_num: 行号
        anime: 动画对象  
        platform_mapping: 平台映射字典，格式为 {"platform": {"name_col": "列名", "url_col": "列名", "name_attr": "属性名", "url_attr": "属性名"}}
    """
    for platform, mapping in platform_mapping.items():
        # 获取条目名称和链接
        name_value = getattr(anime, mapping['name_attr'], None)
        url_value = getattr(anime, mapping['url_attr'], None)
        
        # 如果同时有名称和链接，写入超链接形式
        if is_valid_name(name_value) and url_value:
            success = col_helper.safe_write_hyperlink(row_num, mapping['url_col'], url_value, name_value)
            if success:
                logging.info(f"已写入{platform}超链接: {name_value} -> {url_value}")
            else:
                logging.error(f"Error writing {platform} hyperlink for {anime.original_name[:50]}")
        elif url_value:
            # 如果只有链接没有名称，直接写入链接
            success = col_helper.safe_write(col_helper.ws[row_num], mapping['url_col'], url_value)
            if not success:
                logging.error(f"Error writing {platform} URL for {anime.original_name[:50]}")
        elif is_valid_name(name_value):
            # 如果只有名称没有链接，写入名称
            success = col_helper.safe_write(col_helper.ws[row_num], mapping['url_col'], name_value)
            if not success:
                logging.error(f"Error writing {platform} name for {anime.original_name[:50]}")


def _write_social_media_data(col_helper, row_num, anime):
    """
    写入社交媒体数据（Twitter/X账号和粉丝数）
    Args:
        col_helper: Excel列助手
        row_num: 行号
        anime: 动画对象
    """
    # 处理Twitter/X账号信息
    if anime.twitter_username and anime.twitter_url:
        # 验证Twitter数据有效性
        if TwitterParser.validate_twitter_data(anime.twitter_username, anime.twitter_url):
            # 格式化显示文本（用户名作为超链接文本）
            display_text = TwitterParser.format_twitter_info_for_display(anime.twitter_username, anime.twitter_url)
            
            # 写入Twitter超链接
            success = col_helper.safe_write_hyperlink(row_num, ExcelColumns.X_TWITTER, anime.twitter_url, display_text)
            if success:
                logging.info(f"已写入Twitter超链接: {display_text} -> {anime.twitter_url}")
            else:
                logging.error(f"写入Twitter超链接失败: {anime.original_name[:50]}")
        else:
            logging.warning(f"Twitter数据验证失败，跳过写入: @{anime.twitter_username} ({anime.twitter_url})")
    else:
        logging.debug("没有找到有效的Twitter信息")
    
    # 处理Twitter粉丝数信息 - 只有在Twitter功能启用时才写入
    if hasattr(anime, 'twitter_followers') and anime.twitter_followers:
        try:
            # 检查Twitter功能是否启用
            from utils.core.twitter_config import get_twitter_config
            twitter_config = get_twitter_config()
            
            if twitter_config.is_enabled():
                # 写入粉丝数到X_FAN列
                success = col_helper.safe_write(col_helper.ws[row_num], ExcelColumns.X_FAN, anime.twitter_followers)
                if success:
                    logging.info(f"已写入Twitter粉丝数: {anime.twitter_followers}")
                else:
                    logging.error(f"写入Twitter粉丝数失败: {anime.original_name[:50]}")
            else:
                logging.debug("Twitter功能已禁用，跳过写入粉丝数")
        except Exception as e:
            logging.error(f"写入Twitter粉丝数时出错: {e}")
    else:
        logging.debug("没有找到Twitter粉丝数信息")


def _process_release_date_validation(col_helper, row_num, anime):
    """
    处理放送日期验证和错误记录
    Args:
        col_helper: Excel列助手
        row_num: 行号
        anime: 动画对象
    """
    try:
        # 使用DateValidator进行日期验证
        DateValidator.log_date_validation_result(anime)
        
        # 获取错误信息并写入到错误列（假设错误列名为"日期错误"，需要根据实际情况调整）
        error_message = DateValidator.generate_date_error_message(anime)
        
        # 写入错误信息到Excel
        success = col_helper.safe_write(col_helper.ws[row_num], ExcelColumns.DATE_ERROR, error_message)
        if not success:
            # 如果找不到错误列，尝试使用固定列号作为备选方案
            try:
                col_helper.ws.cell(row=row_num, column=18).value = error_message
            except Exception as e:
                logging.error(f"无法写入日期错误信息: {e}")
        
        # 如果有错误，添加到全局错误列表
        if DateValidator.should_add_to_error_list(anime):
            error_entry = DateValidator.create_date_error_entry(anime)
            if error_entry:
                from utils import date_error
                date_error.append(error_entry)
                
    except Exception as e:
        logging.error(f"处理日期验证时发生错误: {e}")