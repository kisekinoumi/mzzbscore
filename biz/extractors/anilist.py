# extractors/anilist.py
# 存放AniList数据提取逻辑

import logging
from utils import fetch_data_with_retry, LinkParser


def extract_anilist_data(anime, processed_name):
    """
    从AniList提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    # 检查是否已有AniList URL
    if anime.anilist_url:
        anime_id = LinkParser.extract_anilist_id(anime.anilist_url)
        if anime_id:
            logging.info(f"使用已有AniList链接提取数据: {anime.anilist_url}")
            return extract_anilist_data_by_id(anime, anime_id)
    
    # 如果没有链接，则进行搜索
    logging.info(f"通过搜索获取AniList数据: {processed_name}")
    return extract_anilist_data_by_search(anime, processed_name)


def extract_anilist_data_by_id(anime, anime_id):
    """
    通过anime_id直接从AniList API提取数据
    Args:
        anime: Anime对象
        anime_id: AniList条目ID
    Returns:
        bool: 是否成功提取数据
    """
    anilist_url = 'https://graphql.anilist.co'
    
    # 获取基本信息的查询
    basic_query = '''
    query ($id: Int) {
      Media (id: $id) {
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
    '''
    basic_variables = {"id": int(anime_id)}
    
    basic_response = fetch_data_with_retry(
        anilist_url, 
        method='POST', 
        data={'query': basic_query, 'variables': basic_variables}
    )
    
    if not basic_response:
        logging.error(f"AniList条目 {anime_id} 基本信息请求失败")
        anime.score_al = "Request failed"
        return False
    
    try:
        basic_data = basic_response.json()
    except Exception:
        logging.error(f"AniList条目 {anime_id} JSON解析失败")
        anime.score_al = "JSON decode error"
        return False
    
    if 'data' not in basic_data or not basic_data['data']['Media']:
        logging.error(f"AniList条目 {anime_id} 数据为空")
        anime.score_al = "No data found"
        return False
    
    media_data = basic_data['data']['Media']
    
    # 设置基本信息
    anime.anilist_url = f"https://anilist.co/anime/{anime_id}"
    anime.anilist_name = media_data['title']['romaji']
    
    # 处理开播日期
    start_date = media_data.get('startDate', {})
    if start_date.get('year'):
        year = str(start_date['year'])
        month = start_date.get('month')
        if month:
            anime.anilist_subject_Date = f"{year}{month:02d}"
        else:
            anime.anilist_subject_Date = year
        logging.info(f"AniList开播日期: {anime.anilist_subject_Date}")
    
    # 获取详细评分信息
    detail_query = '''
    query ($id: Int) {
      Media (id: $id) {
        averageScore
        stats {
          scoreDistribution {
            score
            amount
          }
        }
      }
    }
    '''
    detail_variables = {"id": int(anime_id)}
    
    detail_response = fetch_data_with_retry(
        anilist_url, 
        method='POST',
        data={'query': detail_query, 'variables': detail_variables}
    )
    
    if detail_response:
        try:
            detail_data = detail_response.json()
            if 'data' in detail_data and 'Media' in detail_data['data']:
                anime_detail = detail_data['data']['Media']
                anime.score_al = anime_detail.get('averageScore', 'No score found')

                # 计算所有分数段的评分人数之和
                total_votes = 0
                stats = anime_detail.get('stats', {})
                score_distribution = stats.get('scoreDistribution', [])

                if score_distribution:
                    for score_data in score_distribution:
                        amount = score_data.get('amount', 0)
                        if amount:
                            total_votes += amount
                    anime.anilist_total = str(total_votes)
                    logging.info(f"计算得到的AniList总评分人数: {total_votes}")
                else:
                    anime.anilist_total = 'No vote data available'
                    logging.warning("无法获取AniList评分分布数据")
            else:
                anime.score_al = 'No AniList results'
                logging.warning("无AniList详细数据")
        except Exception:
            anime.score_al = 'No response results'
            logging.warning("AniList详细数据解析失败")
    else:
        anime.score_al = 'No response results'
        logging.warning("AniList详细数据请求失败")
    
    logging.info(f"AniList链接: {anime.anilist_url}")
    logging.info(f"AniList名称: {anime.anilist_name}")
    logging.info(f"AniList评分: {anime.score_al}")
    logging.info(f"AniList评分人数: {anime.anilist_total}")
    return True


def extract_anilist_data_by_search(anime, processed_name):
    """
    通过搜索从AniList API提取动画评分
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
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

    anilist_search_response = fetch_data_with_retry(
        anilist_url, 
        method='POST', 
        data={'query': anilist_search_query, 'variables': anilist_search_variables}
    )

    if not anilist_search_response:
        anime.score_al = 'Request failed'
        logging.warning("AniList请求失败")
        return False

    try:
        anilist_search_data = anilist_search_response.json()
    except Exception:
        anime.score_al = 'JSON decode error'
        logging.error("AniList搜索结果JSON解析失败")
        return False

    if ('data' not in anilist_search_data or 
        'Page' not in anilist_search_data['data'] or
        not anilist_search_data['data']['Page']['media']):
        anime.score_al = 'No AniList results'
        anime.anilist_total = 'No vote data available'
        logging.warning("AniList无结果")
        return False

    media_list = anilist_search_data['data']['Page']['media']
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
            logging.info(f"选中AniList候选条目名称为{anilist_temp_name},选中AniList候选条目 {candidate['id']}，放送日期: {anime.anilist_subject_Date}")
            break
        else:
            logging.info(f"选中AniList候选条目名称为{anilist_temp_name},AniList候选条目的放送年份 {candidate_year} 不符合要求")
            
    if not candidate_found:
        logging.error("尝试5次后，没有找到放送年份符合要求的 AniList 候选条目")
        anime.score_al = "No acceptable subject found"
        return False
    
    # 使用选中的候选条目继续处理
    first_anime_id = candidate_media['id']
    anime.anilist_url = f"https://anilist.co/anime/{first_anime_id}"
    anime.anilist_name = candidate_media['title']['romaji']
    
    # 使用单独查询获取评分和统计数据
    anilist_detail_query = '''
    query ($id: Int) {
      Media (id: $id) {
        averageScore
        stats {
          scoreDistribution {
            score
            amount
          }
        }
      }
    }
    '''
    anilist_detail_variables = {"id": first_anime_id}
    anilist_detail_response = fetch_data_with_retry(
        anilist_url, 
        method='POST',
        data={'query': anilist_detail_query, 'variables': anilist_detail_variables}
    )
    
    if anilist_detail_response:
        try:
            anilist_detail_data = anilist_detail_response.json()
            if 'data' in anilist_detail_data and 'Media' in anilist_detail_data['data']:
                anime_detail = anilist_detail_data['data']['Media']
                anime.score_al = anime_detail.get('averageScore', 'No score found')

                # 计算所有分数段的评分人数之和
                total_votes = 0
                stats = anime_detail.get('stats', {})
                score_distribution = stats.get('scoreDistribution', [])

                if score_distribution:
                    for score_data in score_distribution:
                        amount = score_data.get('amount', 0)
                        if amount:
                            total_votes += amount
                    anime.anilist_total = str(total_votes)
                    logging.info(f"计算得到的AniList总评分人数: {total_votes}")
                else:
                    anime.anilist_total = 'No vote data available'
                    logging.warning("无法获取AniList评分分布数据")
                
                logging.info("AniList链接: " + str(anime.anilist_url))
                logging.info("AniList名称: " + str(anime.anilist_name))
                logging.info("AniList评分: " + str(anime.score_al))
                logging.info("AniList评分人数: " + str(anime.anilist_total))
                logging.info("AniList开播日期: " + str(anime.anilist_subject_Date))
            else:
                anime.score_al = 'No AniList results'
                logging.warning("无AniList数据")
        except Exception:
            anime.score_al = 'No response results'
            logging.warning("AniList请求失败")
    else:
        anime.score_al = 'Request failed'
        logging.warning("AniList请求失败")
    
    return True