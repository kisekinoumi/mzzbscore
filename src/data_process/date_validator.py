# biz/data_process/date_validator.py
# 日期一致性检查逻辑

import logging


class DateValidator:
    """日期验证器，处理各平台开播日期的一致性检查"""
    
    @staticmethod
    def validate_release_dates(anime):
        """
        验证各平台开播日期的一致性
        Args:
            anime: Anime对象
        Returns:
            dict: 包含验证结果的字典
        """
        dates = {
            'bangumi': anime.bangumi_subject_Date,
            'myanimelist': anime.myanimelist_subject_Date,
            'anilist': anime.anilist_subject_Date,
            'filmarks': anime.filmarks_subject_Date
        }
        
        # 过滤出有效的日期
        valid_dates = {platform: date for platform, date in dates.items() if date}
        
        result = {
            'all_dates': dates,
            'valid_dates': valid_dates,
            'missing_platforms': [],
            'has_inconsistency': False,
            'error_message': '',
            'date_differences': {}
        }
        
        # 检查哪些平台的日期数据缺失
        for platform, date in dates.items():
            if not date:
                result['missing_platforms'].append(platform)
        
        # 如果没有任何有效日期
        if not valid_dates:
            result['error_message'] = "所有平台都没有找到条目"
            return result
        
        # 如果只有一个有效日期
        if len(valid_dates) == 1:
            platform, date = list(valid_dates.items())[0]
            if result['missing_platforms']:
                missing_msg = "/".join(result['missing_platforms']) + "没有找到条目"
                result['error_message'] = missing_msg
            return result
        
        # 检查多个日期是否一致
        date_values = list(valid_dates.values())
        first_date = date_values[0]
        all_same = all(date == first_date for date in date_values)
        
        if all_same:
            # 所有有效日期都相同
            if result['missing_platforms']:
                missing_msg = "/".join(result['missing_platforms']) + "没有找到条目"
                result['error_message'] = missing_msg
        else:
            # 日期不一致
            result['has_inconsistency'] = True
            diff_parts = []
            for platform, date in valid_dates.items():
                diff_parts.append(f"{platform}: {date}")
            
            diff_str = "; ".join(diff_parts)
            result['date_differences'] = valid_dates
            
            if result['missing_platforms']:
                missing_msg = "/".join(result['missing_platforms']) + "没有找到条目"
                result['error_message'] = f"{missing_msg}; {diff_str}"
            else:
                result['error_message'] = diff_str
        
        return result
    
    @staticmethod
    def generate_date_error_message(anime):
        """
        生成日期错误信息
        Args:
            anime: Anime对象
        Returns:
            str: 错误信息字符串，如果没有错误返回空字符串
        """
        validation_result = DateValidator.validate_release_dates(anime)
        return validation_result['error_message']
    
    @staticmethod
    def log_date_validation_result(anime):
        """
        记录日期验证结果到日志
        Args:
            anime: Anime对象
        """
        validation_result = DateValidator.validate_release_dates(anime)
        
        if not validation_result['error_message']:
            if len(validation_result['valid_dates']) > 1:
                logging.info(f"所有平台的开播日期相同: {list(validation_result['valid_dates'].values())[0]}")
            return
        
        if validation_result['missing_platforms']:
            missing_msg = "/".join(validation_result['missing_platforms']) + "没有找到条目"
            logging.info(missing_msg)
        
        if validation_result['has_inconsistency']:
            diff_str = "; ".join([f"{platform}: {date}" for platform, date in validation_result['date_differences'].items()])
            if len(validation_result['valid_dates']) == len(validation_result['all_dates']):
                logging.info("四个平台的开播日期不相同: " + diff_str)
            else:
                logging.info("存在的平台放送日期不相同: " + diff_str)
    
    @staticmethod
    def should_add_to_error_list(anime):
        """
        判断是否应该将此动画的日期问题添加到错误列表
        Args:
            anime: Anime对象
        Returns:
            bool: 是否应该添加到错误列表
        """
        validation_result = DateValidator.validate_release_dates(anime)
        return bool(validation_result['error_message'])
    
    @staticmethod
    def create_date_error_entry(anime):
        """
        创建日期错误条目
        Args:
            anime: Anime对象
        Returns:
            dict or None: 错误条目字典，如果没有错误返回None
        """
        error_message = DateValidator.generate_date_error_message(anime)
        if error_message:
            return {
                "name": anime.original_name,
                "error": error_message
            }
        return None 