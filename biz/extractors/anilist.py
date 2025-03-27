# extractors/anilist.py
# 存放AniList数据提取逻辑

import logging
from utils import fetch_data_with_retry

def extract_anilist_data(anime, processed_name):
    """从AniList API提取动画评。"""
    # 导入全局变量
    from utils.global_variables import ALLOWED_YEARS
    
    anilist_url = 'https://graphql.anilist.co'
    anilist_search_query = '''
    query ($search: String) {
      Page (page: 1, perPage: 5) {
        media (search: $search, type: ANIME) {
          id
          title {
            romaji
          }
          startDate {
            year
            month
          }
        }
      }
    }
    '''
    anilist_search_variables = {
        "search": processed_name  # 使用原始名称进行搜索
    }

    anilist_search_response = fetch_data_with_retry(anilist_url, method='POST', data={'query': anilist_search_query,
                                                                                      'variables': anilist_search_variables})

    if anilist_search_response:
        anilist_search_data = anilist_search_response.json()

        if 'data' in anilist_search_data and 'Page' in anilist_search_data['data']:
            media_list = anilist_search_data['data']['Page']['media']
            if media_list:
                candidate_found = False
                candidate_media = None
                attempts = 0
                for candidate in media_list:
                    attempts += 1
                    if attempts > 5:
                        break
                    anilist_temp_name = candidate['title']['romaji']
                    start_date = candidate.get('startDate', {})
                    candidate_year = str(start_date.get('year')) if start_date.get('year') else None
                    if candidate_year and candidate_year in ALLOWED_YEARS:
                        candidate_found = True
                        candidate_media = candidate
                        candidate_month = start_date.get('month')
                        if candidate_month:
                            anime.anilist_subject_Date = f"{candidate_year}{candidate_month:02d}"
                        else:
                            anime.anilist_subject_Date = candidate_year
                        logging.info(
                            f"选中AniList候选条目名称为{anilist_temp_name},选中AniList候选条目 {candidate['id']}，放送日期: {anime.anilist_subject_Date}")
                        break
                    else:
                        logging.info(
                            f"选中AniList候选条目名称为{anilist_temp_name},AniList候选条目的放送年份 {candidate_year} 不符合要求。")
                if not candidate_found:
                    logging.error("尝试5次后，没有找到放送年份符合要求的 AniList 候选条目。")
                    anime.score_al = "No acceptable subject found"
                    return False
                # 使用选中的候选条目继续处理
                first_anime_id = candidate_media['id']
                anime.anilist_url = f"https://anilist.co/anime/{first_anime_id}"
                anime.anilist_name = candidate_media['title']['romaji']
                # 使用单独查询获取评分和人气数据
                anilist_detail_query = '''
                query ($id: Int) {
                  Media (id: $id) {
                    averageScore
                    popularity
                  }
                }
                '''
                anilist_detail_variables = {"id": first_anime_id}
                anilist_detail_response = fetch_data_with_retry(anilist_url, method='POST',
                                                                data={'query': anilist_detail_query,
                                                                      'variables': anilist_detail_variables})
                if anilist_detail_response:
                    anilist_detail_data = anilist_detail_response.json()
                    if 'data' in anilist_detail_data and 'Media' in anilist_detail_data['data']:
                        anime_detail = anilist_detail_data['data']['Media']
                        anime.score_al = anime_detail.get('averageScore', 'No score found')
                        anime.anilist_total = str(anime_detail.get('popularity', 'No popularity info'))
                        logging.info("AniList链接: " + str(anime.anilist_url))
                        logging.info("AniList名称: " + str(anime.anilist_name))
                        logging.info("AniList评分: " + str(anime.score_al))
                        logging.info("AniList评分人数: " + str(anime.anilist_total))
                        logging.info("AniList开播日期: " + str(anime.anilist_subject_Date))
                    else:
                        anime.score_al = 'No AniList results'
                        logging.warning("无AniList数据")
                else:
                    anime.score_al = 'No response results'
                    logging.warning("AniList请求失败")
            else:
                anime.score_al = 'No AniList results'
                anime.popularity = 'No popularity info'
                logging.warning("AniList无结果")

        else:
            logging.warning("Error with AniList API")
            anime.score_al = 'Error with AniList API'  # API请求出错
    else:
        anime.score_al = 'Request failed'
        logging.warning("AniList请求失败")
    return True