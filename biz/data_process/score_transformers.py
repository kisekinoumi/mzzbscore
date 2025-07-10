# biz/data_process/score_transformers.py
# 各平台评分转换逻辑

import logging
from utils.data_validators import safe_float, is_valid_value


class ScoreTransformer:
    """评分转换器，处理各平台评分的标准化转换"""
    
    @staticmethod
    def anilist_to_standard(score):
        """
        AniList 100分制转10分制
        Args:
            score: AniList原始评分
        Returns:
            str or None: 转换后的10分制评分（保留1位小数），失败时返回None
        """
        if not is_valid_value(score):
            return None
            
        score_float = safe_float(score)
        if score_float is None:
            return None
            
        try:
            converted = score_float / 10
            return f"{converted:.1f}"
        except Exception as e:
            logging.error(f"AniList评分转换失败: {score} -> {e}")
            return None
    
    @staticmethod
    def filmarks_double(score):
        """
        Filmarks评分乘2（转换为10分制）
        Args:
            score: Filmarks原始评分
        Returns:
            float or None: 转换后的评分，失败时返回None
        """
        if not is_valid_value(score):
            return None
            
        score_float = safe_float(score)
        if score_float is None:
            return None
            
        try:
            return score_float * 2
        except Exception as e:
            logging.error(f"Filmarks评分转换失败: {score} -> {e}")
            return None
    
    @staticmethod
    def bangumi_standard(score):
        """
        Bangumi评分标准化（已经是10分制，直接返回）
        Args:
            score: Bangumi原始评分
        Returns:
            float or None: 标准化后的评分，失败时返回None
        """
        if not is_valid_value(score):
            return None
            
        return safe_float(score)
    
    @staticmethod
    def myanimelist_standard(score):
        """
        MyAnimeList评分标准化（已经是10分制，直接返回）
        Args:
            score: MyAnimeList原始评分
        Returns:
            float or None: 标准化后的评分，失败时返回None
        """
        if not is_valid_value(score):
            return None
            
        return safe_float(score)
    
    @staticmethod
    def get_transformed_scores(anime):
        """
        获取所有转换后的评分
        Args:
            anime: Anime对象
        Returns:
            dict: 包含所有转换后评分的字典
        """
        return {
            'bangumi': ScoreTransformer.bangumi_standard(anime.score_bgm),
            'anilist': ScoreTransformer.anilist_to_standard(anime.score_al),
            'myanimelist': ScoreTransformer.myanimelist_standard(anime.score_mal),
            'filmarks': safe_float(anime.score_fm),  # 原始评分
            'filmarks_doubled': ScoreTransformer.filmarks_double(anime.score_fm)  # 乘2后的评分
        }


class TotalCountTransformer:
    """评分人数转换器，处理各平台评分人数的标准化"""
    
    @staticmethod
    def safe_total(total_value):
        """
        安全转换评分人数
        Args:
            total_value: 原始评分人数
        Returns:
            int or None: 转换后的评分人数，失败时返回None
        """
        if not is_valid_value(total_value):
            return None
            
        # 尝试转换为整数
        try:
            if isinstance(total_value, str):
                # 去除可能的逗号分隔符
                clean_value = total_value.replace(',', '').replace(' ', '')
                return int(clean_value)
            return int(total_value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def get_transformed_totals(anime):
        """
        获取所有转换后的评分人数
        Args:
            anime: Anime对象
        Returns:
            dict: 包含所有转换后评分人数的字典
        """
        return {
            'bangumi': TotalCountTransformer.safe_total(anime.bangumi_total),
            'anilist': TotalCountTransformer.safe_total(anime.anilist_total),
            'myanimelist': TotalCountTransformer.safe_total(anime.myanimelist_total),
            'filmarks': TotalCountTransformer.safe_total(anime.filmarks_total)
        } 