# src/data_process/date_validator.py
# 日期一致性检查逻辑（精准区分“平台未找到条目”与“已命中但平台暂无开播月份”）

import logging


class DateValidator:
    """日期验证器，处理各平台开播日期的一致性检查"""

    @staticmethod
    def validate_release_dates(anime):
        """验证各平台开播日期的一致性"""
        dates = {
            "bangumi": anime.bangumi_subject_Date,
            "myanimelist": anime.myanimelist_subject_Date,
            "anilist": anime.anilist_subject_Date,
            "filmarks": anime.filmarks_subject_Date,
        }
        urls = {
            "bangumi": getattr(anime, "bangumi_url", ""),
            "myanimelist": getattr(anime, "myanimelist_url", ""),
            "anilist": getattr(anime, "anilist_url", ""),
            "filmarks": getattr(anime, "filmarks_url", ""),
        }

        valid_dates = {platform: date for platform, date in dates.items() if date}
        missing_platforms = []
        undated_platforms = []

        for platform, date_val in dates.items():
            if not date_val:
                if urls.get(platform):
                    undated_platforms.append(platform)
                else:
                    missing_platforms.append(platform)

        result = {
            "all_dates": dates,
            "valid_dates": valid_dates,
            "missing_platforms": missing_platforms,
            "undated_platforms": undated_platforms,
            "has_inconsistency": False,
            "error_message": "",
            "date_differences": {},
        }

        if not valid_dates and not any(urls.values()):
            result["error_message"] = "所有平台都没有找到条目"
            return result

        msg_parts = []
        if missing_platforms:
            msg_parts.append("/".join(missing_platforms) + "没有找到条目")
        if undated_platforms:
            msg_parts.append("/".join(undated_platforms) + "暂无开播月份")

        if len(valid_dates) > 1:
            date_values = list(valid_dates.values())
            first_date = date_values[0]
            all_same = all(d == first_date for d in date_values)
            if not all_same:
                result["has_inconsistency"] = True
                result["date_differences"] = valid_dates
                diff_str = "; ".join(
                    f"{platform}: {date_val}" for platform, date_val in valid_dates.items()
                )
                msg_parts.append(diff_str)

        result["error_message"] = "; ".join(msg_parts)
        return result

    @staticmethod
    def generate_date_error_message(anime):
        validation_result = DateValidator.validate_release_dates(anime)
        return validation_result["error_message"]

    @staticmethod
    def log_date_validation_result(anime):
        validation_result = DateValidator.validate_release_dates(anime)

        if not validation_result["error_message"]:
            if len(validation_result["valid_dates"]) > 1:
                logging.info(
                    f"所有平台的开播日期相同: {list(validation_result['valid_dates'].values())[0]}"
                )
            return

        if validation_result["missing_platforms"]:
            logging.info("/".join(validation_result["missing_platforms"]) + "没有找到条目")
        if validation_result["undated_platforms"]:
            logging.info("/".join(validation_result["undated_platforms"]) + "暂无开播月份")

        if validation_result["has_inconsistency"]:
            diff_str = "; ".join(
                [
                    f"{platform}: {date}"
                    for platform, date in validation_result["date_differences"].items()
                ]
            )
            if len(validation_result["valid_dates"]) == len(validation_result["all_dates"]):
                logging.info("四个平台的开播日期不相同: " + diff_str)
            else:
                logging.info("存在的平台放送日期不相同: " + diff_str)

    @staticmethod
    def should_add_to_error_list(anime):
        validation_result = DateValidator.validate_release_dates(anime)
        return bool(validation_result["error_message"])

    @staticmethod
    def create_date_error_entry(anime):
        error_message = DateValidator.generate_date_error_message(anime)
        if error_message:
            return {
                "name": anime.original_name,
                "error": error_message,
            }
        return None
