# -*- coding: utf-8 -*-
import concurrent.futures
import glob
from html import unescape
import io
import logging as std_logging
import os
import re
import sys
import time
from typing import List, Tuple

def _configure_console_utf8() -> None:
    """设置控制台 UTF-8 编码（仅在 CLI 主入口调用，避免模块导入时关闭测试框架捕获流）"""
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if sys.platform == "win32":
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream is None:
                continue
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                    continue
                except Exception:
                    pass
            if hasattr(stream, "buffer"):
                setattr(sys, stream_name, io.TextIOWrapper(stream.buffer, encoding="utf-8"))

# 表格模板格式，如果修改值要求使用者更新表格文件
FORMAT_VERSION = 20260410

from openpyxl import load_workbook
import pandas as pd

from models import Anime
from src.data_process.excel_handler import update_excel_data
from src.extractors import (
    TwitterFollowersHelper,
    extract_anilist_data,
    extract_bangumi_data,
    extract_filmarks_data,
    extract_myanimelist_data,
)
from src.extractors.myanimelist import MyAnimeListExtractor
from utils import (
    ExcelColumnHelper,
    UrlChecker,
    date_error,
    get_template_version,
    preprocess_name,
    setup_logger,
    setup_myanimelist_api_config,
    setup_twitter_config,
)
from utils.core.global_variables import FILE_PATH, update_constants
from utils.network import (
    check_update,
    close_all_http_sessions,
    get_proxy_status,
    is_twitter_accessible,
    setup_proxy,
)

# 平台未命中错误状态集合（仅对“未搜到/无合规候选”触发跨站兜底重搜，不对网络/鉴权故障重复轰炸）
MAL_NOT_FOUND_ERRORS = {"No acceptable subject found", "No results found"}
ANILIST_NOT_FOUND_ERRORS = {"No acceptable subject found", "No AniList results"}
BANGUMI_NOT_FOUND_ERRORS = {"No acceptable subject found", "No results found"}
FILMARKS_NOT_FOUND_ERRORS = {"No acceptable subject found", "No results found"}
INVALID_FALLBACK_TITLES = {"", "No name found", "未知名称", None}


def _is_mal_not_found(anime: Anime) -> bool:
    return anime.score_mal in MAL_NOT_FOUND_ERRORS and not anime.myanimelist_url


def _is_anilist_not_found(anime: Anime) -> bool:
    return anime.score_al in ANILIST_NOT_FOUND_ERRORS and not anime.anilist_url


def _is_bangumi_not_found(anime: Anime) -> bool:
    return anime.score_bgm in BANGUMI_NOT_FOUND_ERRORS and not anime.bangumi_url


def _is_filmarks_not_found(anime: Anime) -> bool:
    return anime.score_fm in FILMARKS_NOT_FOUND_ERRORS and not anime.filmarks_url


def _is_valid_fallback_title(title) -> bool:
    return title not in INVALID_FALLBACK_TITLES and bool(str(title).strip())


def _search_dedupe_key(title: str) -> str:
    """
    用于跨站重搜词去重的键：去空白标点并转小写，但不做 NFKC 折叠，
    以保留 'actII' vs 'actⅡ'、'冰' vs '氷' 等会影响搜索引擎分词命中的字形差异。
    """
    if not title:
        return ""
    cleaned = re.sub(
        r"[\s\-_~:：;；,，、。.!！?？'\"“”‘’\[\]【】()（）<>〈〉《》「」『』/\\|・･☆★♪…·〜～&#]",
        "",
        str(title).strip(),
    )
    return "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in cleaned)


def _collect_cross_platform_titles(
    anime: Anime,
    *,
    already_searched_norms: set,
    prefer_english_last: bool = True,
) -> List[Tuple[str, str]]:
    """
    收集其他已成功匹配的平台返回的可信标题（日文名、罗马音/原始名、英文名），
    按归一化键去重并跳过已搜索过的原名，供跨站兜底重搜使用。
    """
    jp_sources = [
        ("AniList日文标题", getattr(anime, "anilist_japanese_name", "") or anime.anilist_name),
        ("MAL日文标题", getattr(anime, "myanimelist_japanese_name", "") or anime.myanimelist_name),
        ("Bangumi日文标题", anime.bangumi_name),
        ("Filmarks标题", anime.filmarks_name),
    ]
    romaji_sources = [
        ("AniList罗马音标题", getattr(anime, "anilist_romaji_name", "")),
        ("Filmarks原名标题", getattr(anime, "filmarks_original_name", "")),
    ]
    en_sources = [
        ("AniList英文标题", getattr(anime, "anilist_english_name", "")),
        ("MAL英文标题", getattr(anime, "myanimelist_english_name", "")),
    ]

    ordered = (
        jp_sources + romaji_sources + en_sources
        if prefer_english_last
        else jp_sources + en_sources + romaji_sources
    )

    deduped: List[Tuple[str, str]] = []
    seen = set(already_searched_norms)
    for label, raw_title in ordered:
        if not _is_valid_fallback_title(raw_title):
            continue
        clean = unescape(str(raw_title).strip())
        dedupe_key = _search_dedupe_key(clean)
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append((label, clean))
    return deduped


def _retry_myanimelist_with_anilist_titles(anime: Anime, logger=None) -> None:
    """兼容旧接口：MAL失败时先用idMal直连验证，再用跨站日/罗/英标题兜底"""
    log = logger or std_logging.getLogger()
    if not _is_mal_not_found(anime):
        return

    if getattr(anime, "id_mal", ""):
        if MyAnimeListExtractor().extract_by_id_mal_verified(anime, anime.id_mal):
            return

    searched = {_search_dedupe_key(anime.original_name)}
    for title_type, title in _collect_cross_platform_titles(
        anime, already_searched_norms=searched, prefer_english_last=False
    ):
        if not _is_mal_not_found(anime):
            break
        log.info(f"MAL候选未找到，尝试使用{title_type}重新搜索 MAL: {title}")
        extract_myanimelist_data(anime, preprocess_name(title))


def _retry_anilist_with_myanimelist_titles(anime: Anime, logger=None) -> None:
    """兼容旧接口：AniList失败时使用跨站日/英/原名标题兜底"""
    log = logger or std_logging.getLogger()
    if not _is_anilist_not_found(anime):
        return

    searched = {_search_dedupe_key(anime.original_name)}
    for title_type, title in _collect_cross_platform_titles(
        anime, already_searched_norms=searched, prefer_english_last=False
    ):
        if not _is_anilist_not_found(anime):
            break
        log.info(f"AniList候选未找到，尝试使用{title_type}重新搜索 AniList: {title}")
        extract_anilist_data(anime, preprocess_name(title))


def run_cross_platform_fallbacks(anime: Anime, logger=None) -> None:
    """
    四站全覆盖跨站协同兜底（参照 anime-score-aggregator 的 idMal 交叉与跨站标题兜底）：
    1. 若 AniList 已带回 idMal 且 MAL 未命中 -> 直接按 idMal 精准拉取验证
    2. 对 AniList / MAL / Bangumi / Filmarks 中未命中的平台，利用已命中平台返回的异体/日文/罗马音/英文标题重搜
    3. 若 AniList 在兜底轮新命中并拿到 idMal，再次补救一次仍未命中的 MAL
    """
    log = logger or std_logging.getLogger()

    # 1. idMal 直连补位
    if _is_mal_not_found(anime) and getattr(anime, "id_mal", ""):
        MyAnimeListExtractor().extract_by_id_mal_verified(anime, anime.id_mal)

    # 2. AniList 跨站标题兜底（优先救回 AniList，因其可能提供 idMal 和 Twitter 链接）
    if _is_anilist_not_found(anime):
        _retry_anilist_with_myanimelist_titles(anime, logger=log)
        if _is_mal_not_found(anime) and getattr(anime, "id_mal", ""):
            MyAnimeListExtractor().extract_by_id_mal_verified(anime, anime.id_mal)

    # 3. MAL 跨站标题兜底
    if _is_mal_not_found(anime):
        _retry_myanimelist_with_anilist_titles(anime, logger=log)

    # 4. Bangumi 跨站标题兜底（优先使用日文/罗马音标题，最多尝试前 3 个相异标题）
    if _is_bangumi_not_found(anime):
        searched = {_search_dedupe_key(anime.original_name)}
        for title_type, title in _collect_cross_platform_titles(
            anime, already_searched_norms=searched, prefer_english_last=True
        )[:3]:
            if not _is_bangumi_not_found(anime):
                break
            log.info(f"Bangumi候选未找到，尝试使用{title_type}重新搜索 Bangumi: {title}")
            extract_bangumi_data(anime, preprocess_name(title))

    # 5. Filmarks 跨站标题兜底（优先使用日文/原名标题，最多尝试前 2 个相异标题）
    if _is_filmarks_not_found(anime):
        searched = {_search_dedupe_key(anime.original_name)}
        for title_type, title in _collect_cross_platform_titles(
            anime, already_searched_norms=searched, prefer_english_last=True
        )[:2]:
            if not _is_filmarks_not_found(anime):
                break
            log.info(f"Filmarks候选未找到，尝试使用{title_type}重新搜索 Filmarks: {title}")
            extract_filmarks_data(anime, preprocess_name(title))


def process_single_anime(
    anime: Anime,
    *,
    twitter_config_success: bool = False,
    logger=None,
) -> Anime:
    """对单部 Anime 执行四站并发提取 + 跨站协同兜底 + Twitter 粉丝采集"""
    log = logger or std_logging.getLogger()
    processed_name = preprocess_name(anime.original_name)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_extractor = {
            executor.submit(extract_bangumi_data, anime, processed_name): "bangumi",
            executor.submit(extract_myanimelist_data, anime, processed_name): "myanimelist",
            executor.submit(extract_anilist_data, anime, processed_name): "anilist",
            executor.submit(extract_filmarks_data, anime, processed_name): "filmarks",
        }
        for future in concurrent.futures.as_completed(future_to_extractor):
            extractor_name = future_to_extractor[future]
            try:
                future.result()
                log.info(f"{extractor_name} extractor completed")
            except Exception as exc:
                log.error(f"{extractor_name} extractor generated an exception: {exc}")

    # 四站协同兜底（idMal直连 + 跨站标题重搜）
    run_cross_platform_fallbacks(anime, logger=log)

    # 获取Twitter粉丝数
    if hasattr(anime, "twitter_username") and anime.twitter_username:
        if not is_twitter_accessible():
            log.info(
                f"发现Twitter账号 @{anime.twitter_username}，但Twitter网络不可用，跳过粉丝数获取"
            )
            anime.twitter_followers = "网络不可用"
        elif twitter_config_success:
            try:
                followers_count = TwitterFollowersHelper.get_followers_count(anime.twitter_username)
                if followers_count is not None:
                    anime.twitter_followers = followers_count
                else:
                    log.warning(f"无法获取 @{anime.twitter_username} 的粉丝数")
                    anime.twitter_followers = "获取失败"
            except Exception as e:
                log.error(f"获取Twitter粉丝数时出错: {e}")
                anime.twitter_followers = "获取出错"
        else:
            log.info(
                f"发现Twitter账号 @{anime.twitter_username}，但Twitter配置未成功，跳过粉丝数获取"
            )
            anime.twitter_followers = "配置未成功"

    return anime


def main() -> None:
    _configure_console_utf8()
    logging = setup_logger()

    # 第一步：代理检测和配置
    try:
        proxy_config = setup_proxy()
        if proxy_config:
            logging.info(f"✅ 代理配置完成 - {get_proxy_status()}")
        else:
            logging.info(f"📡 网络配置完成 - {get_proxy_status()}")
    except Exception as e:
        logging.error(f"代理配置过程中出现错误: {e}")
        logging.info("程序将使用直连模式继续运行")

    check_update()
    logging.info("=" * 50)
    date_error.clear()

    wb = None
    try:
        logging.info("程序开始运行...")

        mal_config_success = setup_myanimelist_api_config()
        if not mal_config_success:
            logging.warning("MyAnimeList API未完成配置，MAL将仅使用网页解析兜底")

        twitter_config_success = False
        if not is_twitter_accessible():
            logging.warning("Twitter网络不可用，跳过Twitter粉丝数获取功能配置")
        else:
            try:
                twitter_config_success = setup_twitter_config()
                if not twitter_config_success:
                    logging.warning("Twitter配置失败，将跳过Twitter粉丝数获取功能")
            except Exception as e:
                logging.error(f"Twitter配置过程中出现错误: {e}")
                logging.info("程序将继续运行其他功能")
                twitter_config_success = False

        logging.info("📋 开始处理动画数据...")

        try:
            wb = load_workbook(FILE_PATH)
            logging.info(f"成功加载Excel文件: {FILE_PATH}")
        except Exception as e:
            logging.error(f"无法加载Excel文件 {FILE_PATH}: {e}")
            logging.error("请检查Excel文件是否存在且格式正确")
            raise
        ws = wb.active

        col_helper = ExcelColumnHelper(ws)

        # 检查表格格式版本（自动兼容 mzzb.xlsx [M1]、首月评分 [L1]、完结评分 [R1]）
        excel_version = get_template_version(ws, col_helper)
        if excel_version != FORMAT_VERSION:
            logging.error(
                f"表格模板版本不匹配！当前代码要求表格文件模板版本为 {FORMAT_VERSION}，"
                f"但表格模板版本为 {excel_version}。请更新表格模板后重试。"
            )
            logging.error(
                "请访问: https://github.com/kisekinoumi/mzzbscore/releases 下载最新版本的表格模板。"
            )
            raise SystemExit(1)

        # 读取 A1 表头设置目标年份及可选目标月份（如 "2026年10月新番..."）
        update_constants(str(ws["A1"].value or ""))

        df = pd.read_excel(FILE_PATH, skiprows=1)
        date_error.clear()

        for index, row in df.iterrows():
            if pd.isna(row["原名"]):
                logging.warning(f"Skipping row {index} because the original name is NaN.")
                continue

            anime = Anime(original_name=str(row["原名"]).strip())
            logging.info(str(anime))

            excel_row = ws[index + 3]
            existing_urls = UrlChecker.check_row_urls(excel_row, col_helper)

            if existing_urls["bangumi"]:
                anime.bangumi_url = existing_urls["bangumi"]
            if existing_urls["anilist"]:
                anime.anilist_url = existing_urls["anilist"]
            if existing_urls["myanimelist"]:
                anime.myanimelist_url = existing_urls["myanimelist"]
            if existing_urls["filmarks"]:
                anime.filmarks_url = existing_urls["filmarks"]

            has_existing_links = UrlChecker.has_any_url(existing_urls)
            available_platforms = UrlChecker.get_available_platforms(existing_urls)
            if has_existing_links:
                logging.info(f"发现已有链接的平台: {', '.join(available_platforms)}")
            else:
                logging.info("未发现已有链接，将进行搜索模式")

            process_single_anime(
                anime,
                twitter_config_success=twitter_config_success,
                logger=logging,
            )

            update_excel_data(ws, index, anime, col_helper)
            time.sleep(0.05)

    except Exception as e:
        logging.error(f"发生错误: {e}")

    finally:
        if wb is not None:
            try:
                wb.save(FILE_PATH)
                logging.info("Excel表格已成功更新。")
            except Exception as e:
                logging.error(f"保存Excel文件时发生错误: {e}")
        else:
            logging.warning("Excel文件未成功加载，跳过保存操作")

        try:
            if date_error:
                logging.info("\n" + "=" * 50)
                logging.info("日期错误汇总 (共 %d 条):" % len(date_error))
                logging.info("=" * 50)
                for i, error in enumerate(date_error, 1):
                    logging.info("%d. 作品：%s" % (i, error["name"]))
                    logging.info("   错误：%s" % error["error"])
                    logging.info("-" * 50)
            else:
                logging.info("没有发现任何日期错误！")
        except Exception as e:
            logging.error(f"输出日期错误信息时发生错误: {e}")

        # 先释放 Scweet 实例与所有线程 HTTP Session，再清理临时数据库文件
        try:
            TwitterFollowersHelper.close()
        except Exception as e:
            logging.debug(f"关闭 Twitter 实例时出现异常: {e}")

        try:
            close_all_http_sessions()
        except Exception as e:
            logging.debug(f"关闭 HTTP 连接池时出现异常: {e}")

        try:
            db_files = glob.glob("scweet_state.db*")
            for db_file in db_files:
                try:
                    os.remove(db_file)
                except Exception as e:
                    logging.warning(f"清理临时文件 {db_file} 时发生错误: {e}，失败")
        except Exception as e:
            logging.warning(f"查找或清理 Scweet 临时文件时发生错误: {e}，失败")

        try:
            while True:
                user_input = input("输入 'exit' 退出程序: ")
                if user_input.lower() == "exit":
                    break
            logging.info("程序已退出...")
        except EOFError:
            logging.info("检测到非交互式终端，程序自动退出...")
        except KeyboardInterrupt:
            logging.info("程序被用户中断...")
        except Exception as e:
            logging.error(f"退出处理时发生错误: {e}")
            logging.info("程序异常退出...")


if __name__ == "__main__":
    main()
