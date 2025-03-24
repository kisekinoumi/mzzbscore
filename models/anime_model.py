# models/anime_model.py
# 存放动画数据模型定义

class Anime:
    def __init__(self, original_name, score_bgm='', score_al='', score_mal='', score_fm='',
                 bangumi_url='', anilist_url='', myanimelist_url='', filmarks_url='',
                 bangumi_name='', anilist_name='', myanimelist_name='', flimarks_name='',
                 bangumi_total='', anilist_total='', myanimelist_total='', filmarks_total='',
                 bangumi_subject_Date='', myanimelist_subject_Date='', anilist_subject_Date='',
                 filmarks_subject_Date=''):
        self.original_name = original_name  # 原始名称
        self.score_bgm = score_bgm  # Bangumi 评分
        self.score_al = score_al  # AniList 评分
        self.score_mal = score_mal  # MyAnimeList 评分
        self.score_fm = score_fm  # Filmarks 评分
        self.bangumi_url = bangumi_url  # Bangumi 条目链接
        self.anilist_url = anilist_url  # AniList 条目链接
        self.myanimelist_url = myanimelist_url  # MyAnimeList 条目链接
        self.filmarks_url = filmarks_url  # Filmarks 条目链接
        self.bangumi_name = bangumi_name  # Bangumi 名称
        self.anilist_name = anilist_name  # AniList 名称
        self.myanimelist_name = myanimelist_name  # MyAnimeList 名称
        self.flimarks_name = flimarks_name  # Filmarks 名称
        self.bangumi_total = bangumi_total  # Bangumi 评分人数
        self.anilist_total = anilist_total  # AniList 人气/评分人数
        self.myanimelist_total = myanimelist_total  # MyAnimeList 评分人数
        self.filmarks_total = filmarks_total  # Filmarks 评分人数
        # 开播日期统一格式为 "YYYYMM"
        self.bangumi_subject_Date = bangumi_subject_Date
        self.myanimelist_subject_Date = myanimelist_subject_Date
        self.anilist_subject_Date = anilist_subject_Date
        self.filmarks_subject_Date = filmarks_subject_Date

    def __str__(self):
        return (f"Anime({self.original_name}, BGM: {self.score_bgm}, AL: {self.score_al}, "
                f"MAL: {self.score_mal}, FM: {self.score_fm}, "
                f"URLs: {self.bangumi_url}, {self.anilist_url}, {self.myanimelist_url}, {self.filmarks_url}, "
                f"Names: {self.bangumi_name}, {self.anilist_name}, {self.myanimelist_name}, {self.flimarks_name}, "
                f"StartDates: BGM:{self.bangumi_subject_Date}, MAL:{self.myanimelist_subject_Date}, "
                f"AL:{self.anilist_subject_Date}, FM:{self.filmarks_subject_Date})")