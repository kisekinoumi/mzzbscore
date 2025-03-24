# excel_handler.py
# 存放Excel处理相关的逻辑

import logging

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
            logging.error(f"Error writing Filmarks \"乘2\"分数 for {anime.original_name[:50]}: {e}")
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
                ws.cell(row=index + 3, column=14).hyperlink = anime.bangumi_url
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
                ws.cell(row=index + 3, column=15).hyperlink = anime.anilist_url
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
                ws.cell(row=index + 3, column=16).hyperlink = anime.myanimelist_url
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
                ws.cell(row=index + 3, column=17).hyperlink = anime.filmarks_url
        except Exception as e:
            logging.error(f"Error writing Filmarks URL for {anime.original_name[:50]}: {e}")

        # ---------------------放送日期写入---------------------
        try:
            error_cell = ws.cell(row=index + 3, column=18)

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
                from main import date_error
                date_error.append({
                    "name": anime.original_name,
                    "error": error_message
                })

        except Exception as e:
            logging.error(f"在处理索引 {index} 时发生错误: {e}")
            pass