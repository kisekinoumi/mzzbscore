# extractors/bangumi.py
# 存放Bangumi数据提取逻辑

import re
import logging
import requests
from utils import fetch_data_with_retry, LinkParser


def extract_bangumi_data(anime, processed_name):
    """
    从Bangumi提取动画评分（统一入口）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    # 检查是否已有Bangumi URL
    if anime.bangumi_url:
        subject_id = LinkParser.extract_bangumi_id(anime.bangumi_url)
        if subject_id:
            logging.info(f"使用已有Bangumi链接提取数据: {anime.bangumi_url}")
            return extract_bangumi_data_by_id(anime, subject_id)
    
    # 如果没有链接，则进行搜索
    logging.info(f"通过搜索获取Bangumi数据: {processed_name}")
    return extract_bangumi_data_by_search(anime, processed_name)


def extract_bangumi_data_by_id(anime, subject_id):
    """
    通过subject_id直接从Bangumi API提取数据
    Args:
        anime: Anime对象
        subject_id: Bangumi条目ID
    Returns:
        bool: 是否成功提取数据
    """
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42'
    }
    
    subject_url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
    subject_response = fetch_data_with_retry(url=subject_url, headers=headers)
    
    if not subject_response:
        logging.error(f"Bangumi条目 {subject_id} 请求失败")
        anime.score_bgm = "Request failed"
        return False
    
    try:
        subject_data = subject_response.json()
    except requests.exceptions.JSONDecodeError:
        logging.error(f"Bangumi条目 {subject_id} JSON解析失败")
        anime.score_bgm = "JSON decode error"
        return False
    
    # 处理基本信息
    anime.bangumi_url = f"https://bgm.tv/subject/{subject_id}"
    anime.bangumi_name = subject_data.get('name', 'No name found')
    
    # 处理开播日期
    if "date" in subject_data and isinstance(subject_data["date"], str):
        date_str = subject_data["date"]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            year = date_str[:4]
            month = date_str[5:7]
            anime.bangumi_subject_Date = year + month
            logging.info(f"Bangumi开播日期: {anime.bangumi_subject_Date}")
        else:
            logging.warning(f"Bangumi日期格式不正确: {date_str}")
    
    # 处理评分信息
    if ('rating' in subject_data and
            'count' in subject_data['rating'] and
            subject_data['rating']['count'] and
            subject_data['rating']['total']):
        total = subject_data['rating']['total']
        score_counts = subject_data['rating']['count']
        weighted_sum = sum(int(score) * int(count) for score, count in score_counts.items())
        calculated_score = round(weighted_sum / total, 2)
        anime.score_bgm = f"{calculated_score:.2f}"
        anime.bangumi_total = str(total)
        logging.info(f"Bangumi评分: {anime.score_bgm}")
        logging.info(f"Bangumi评分人数: {anime.bangumi_total}")
    else:
        anime.score_bgm = 'No score available'
        logging.warning("Bangumi条目无评分信息")
    
    logging.info(f"Bangumi链接: {anime.bangumi_url}")
    logging.info(f"Bangumi名称: {anime.bangumi_name}")
    return True


def extract_bangumi_data_by_search(anime, processed_name):
    """
    通过搜索从Bangumi v0 API提取动画评分（如果放送年份不在 ALLOWED_YEARS 中则选择下一个条目，最多尝试5次）
    Args:
        anime: Anime对象
        processed_name: 预处理后的名称
    Returns:
        bool: 是否成功提取数据
    """
    # 导入全局变量
    from utils.global_variables import ALLOWED_YEARS

    search_url = "https://api.bgm.tv/v0/search/subjects"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42'
    }
    
    # 设置请求体，尝试获取最多 5 个条目
    search_data = {
        "keyword": processed_name,
        "filter": {"type": [2]}
    }
    search_response = fetch_data_with_retry(
        url=search_url,
        method='POST',
        params={"limit": 5},
        data=search_data,
        headers=headers
    )

    if not search_response:
        anime.score_bgm = 'Request failed'
        logging.warning("Bangumi请求失败")
        return False

    try:
        search_result = search_response.json()
        # 保存返回数据到文件方便调试（可选）
        with open("outporiginal_name.html", "w", encoding="utf-8") as f:
            f.write(search_response.text)
    except requests.exceptions.JSONDecodeError:
        logging.error(f"Bangumi搜索结果JSON解析失败: {anime.original_name}")
        anime.score_bgm = "JSON decode error"
        return False

    if 'data' not in search_result or not search_result['data']:
        anime.score_bgm = 'No results found'
        logging.warning("Bangumi无结果")
        return False

    # 查找符合年份要求的候选条目
    subjects = search_result['data']
    candidate_found = False
    candidate_subject_data = None
    candidate_subject = None
    attempts = 0

    # 遍历候选条目，最多尝试 5 个
    for candidate in subjects:
        attempts += 1
        candidate_id = candidate['id']
        subject_url = f"https://api.bgm.tv/v0/subjects/{candidate_id}"
        subject_response = fetch_data_with_retry(url=subject_url, headers=headers)
        
        if not subject_response:
            logging.warning(f"候选条目 {candidate_id} 的详情请求失败")
            if attempts >= 5:
                break
            continue
            
        try:
            candidate_subject_data = subject_response.json()
        except requests.exceptions.JSONDecodeError:
            logging.error(f"候选条目 {candidate_id} JSON解析失败")
            if attempts >= 5:
                break
            continue

        # 判断候选数据中是否有 "date" 字段且格式为 YYYY-MM-DD
        if "date" in candidate_subject_data and isinstance(candidate_subject_data["date"], str):
            bgm_subject_cname = candidate.get('name_cn', 'No name found')
            date_str = candidate_subject_data["date"]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                year = date_str[:4]
                # 使用全局变量 ALLOWED_YEARS 判断年份是否符合要求
                if year in ALLOWED_YEARS:
                    candidate_found = True
                    candidate_subject = candidate
                    anime.bangumi_subject_Date = year + date_str[5:7]  # 转换为 "YYYYMM"
                    logging.info(f"选中条目名称{bgm_subject_cname},选中候选条目 {candidate_id}，放送日期: {anime.bangumi_subject_Date}")
                    break
                else:
                    logging.info(f"选中条目名称{bgm_subject_cname},候选条目 {candidate_id} 的放送年份 {year} 不符合要求")
            else:
                logging.info(f"选中条目名称{bgm_subject_cname},候选条目 {candidate_id} 的放送日期格式不正确: {date_str}")
        else:
            logging.info(f"候选条目 {candidate_id} 缺少 'date' 字段")
            
        if attempts >= 5:
            break

    if not candidate_found:
        logging.error("尝试5次后，没有找到放送年份在 {} 的候选条目".format("/".join(ALLOWED_YEARS)))
        anime.score_bgm = "No acceptable subject found"
        return False

    # 使用选中的候选条目继续处理
    first_subject_id = candidate_subject['id']
    anime.bangumi_url = f"https://bgm.tv/subject/{first_subject_id}"
    anime.bangumi_name = candidate_subject.get('name', 'No name found')
    logging.info("选中Bangumi链接: " + str(anime.bangumi_url))
    logging.info("选中Bangumi名称: " + str(anime.bangumi_name))

    # 处理评分信息
    if ('rating' in candidate_subject_data and
            'count' in candidate_subject_data['rating'] and
            candidate_subject_data['rating']['count'] and
            candidate_subject_data['rating']['total']):
        total = candidate_subject_data['rating']['total']
        score_counts = candidate_subject_data['rating']['count']
        weighted_sum = sum(int(score) * int(count) for score, count in score_counts.items())
        calculated_score = round(weighted_sum / total, 2)
        anime.score_bgm = f"{calculated_score:.2f}"
        anime.bangumi_total = str(total)
        logging.info("Bangumi页面评分: " + str(candidate_subject_data['rating'].get('score')))
        logging.info("Bangumi评分: " + str(anime.score_bgm))
        logging.info("Bangumi评分人数: " + str(anime.bangumi_total))
    else:
        anime.score_bgm = 'No score available'
        logging.warning("选中条目无评分信息")
        
    return True