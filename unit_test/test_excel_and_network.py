# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import MagicMock, patch

from openpyxl import Workbook, load_workbook

from models import Anime
from src.data_process.date_validator import DateValidator
from src.data_process.excel_handler import update_excel_data
from utils.excel.excel_columns import ExcelColumns
from utils.excel.excel_utils import ExcelColumnHelper, get_template_version
from utils.network.network import (
    SiteRateLimiter,
    _rate_limiter,
    clear_request_cache,
    fetch_data_with_retry,
    parse_retry_after,
)


def test_get_template_version_across_all_three_official_templates():
    repo_root = Path(__file__).resolve().parent.parent
    for filename in ("mzzb.xlsx", "X月新番首月评分.xlsx", "X月新番完结评分.xlsx"):
        wb = load_workbook(repo_root / filename, read_only=False)
        ws = wb.active
        helper = ExcelColumnHelper(ws)
        assert get_template_version(ws, helper) == 20260410
        wb.close()


def test_excel_translated_name_backfill_only_when_empty():
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "2026年10月新番首月评分"
    headers = [
        ExcelColumns.ORIGINAL_NAME,
        ExcelColumns.TRANSLATED_NAME,
        ExcelColumns.BANGUMI_SCORE,
        ExcelColumns.BANGUMI_TOTAL,
        ExcelColumns.ANILIST_SCORE,
        ExcelColumns.ANILIST_TOTAL,
        ExcelColumns.MYANIMELIST_SCORE,
        ExcelColumns.MYANIMELIST_TOTAL,
        ExcelColumns.FILMARKS_SCORE,
        ExcelColumns.FILMARKS_TOTAL,
        ExcelColumns.BANGUMI_URL,
        ExcelColumns.ANILIST_URL,
        ExcelColumns.MYANIMELIST_URL,
        ExcelColumns.FILMARKS_URL,
        ExcelColumns.X_TWITTER,
        ExcelColumns.X_FAN,
        ExcelColumns.DATE_ERROR,
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.cell(row=2, column=col_idx, value=h)

    # Row 3: 译名为空 -> 自动填入 Bangumi 中文名
    ws.cell(row=3, column=1, value="薬屋のひとりごと 第3期（第1クール）")
    ws.cell(row=3, column=2, value=None)

    # Row 4: 译名已有用户内容 -> 绝不覆盖！
    ws.cell(row=4, column=1, value="アオのハコ Season2")
    ws.cell(row=4, column=2, value="青春之箱 第二季（人工精校）")

    helper = ExcelColumnHelper(ws)

    anime1 = Anime(original_name="薬屋のひとりごと 第3期（第1クール）")
    anime1.bangumi_chinese_name = "药屋少女的呢喃 第三季"
    anime1.bangumi_name = "薬屋のひとりごと 第3期"
    anime1.bangumi_url = "https://bgm.tv/subject/500001"
    anime1.score_bgm = "8.15"
    anime1.bangumi_total = "120"
    anime1.score_fm = "4.2"
    anime1.filmarks_total = "80"

    anime2 = Anime(original_name="アオのハコ Season2")
    anime2.bangumi_chinese_name = "蓝箱 第二季"
    anime2.bangumi_name = "アオのハコ 第2期"
    anime2.bangumi_url = "https://bgm.tv/subject/500002"
    anime2.score_bgm = "7.90"
    anime2.bangumi_total = "30"  # < 50 票应转为 "NaN"

    update_excel_data(ws, 0, anime1, helper)
    update_excel_data(ws, 1, anime2, helper)

    assert ws.cell(row=3, column=2).value == "药屋少女的呢喃 第三季"
    assert ws.cell(row=4, column=2).value == "青春之箱 第二季（人工精校）"
    # 验证 < 50 票置为 "NaN" 且无 Filmarks原始评分 列时不报错、Filmarks 2倍制正常写入
    assert ws.cell(row=3, column=3).value == 8.15
    assert ws.cell(row=3, column=9).value == 8.4
    assert ws.cell(row=4, column=3).value == "NaN"
    assert ws.cell(row=4, column=4).value == "NaN"


def test_date_validator_distinguishes_missing_vs_undated():
    anime = Anime(original_name="未定月アニメ")
    anime.bangumi_url = "https://bgm.tv/subject/1"
    anime.bangumi_subject_Date = "202610"
    anime.anilist_url = "https://anilist.co/anime/2"
    anime.anilist_subject_Date = "202610"
    anime.myanimelist_url = "https://myanimelist.net/anime/3"
    anime.myanimelist_subject_Date = ""  # 已找到条目但暂无月份
    anime.filmarks_url = ""  # 未找到条目
    anime.filmarks_subject_Date = ""

    msg = DateValidator.generate_date_error_message(anime)
    assert "filmarks没有找到条目" in msg
    assert "myanimelist暂无开播月份" in msg
    assert "myanimelist没有找到条目" not in msg


def test_network_non_retryable_404_and_retry_after_parsing():
    assert parse_retry_after({"Retry-After": "7"}, default_seconds=3.0) == 7.0
    assert parse_retry_after({}, default_seconds=4.0) == 4.0

    limiter = SiteRateLimiter()
    limiter.observe_response_headers(
        "anilist", {"X-RateLimit-Limit": "30", "X-RateLimit-Remaining": "2"}
    )

    clear_request_cache()
    _rate_limiter.reset()

    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.headers = {}

    fake_session = MagicMock()
    fake_session.get.return_value = fake_resp

    with (
        patch("utils.network.network._get_http_session", return_value=fake_session),
        patch("utils.network.network.time.sleep") as mock_sleep,
    ):
        res_none = fetch_data_with_retry("https://api.myanimelist.net/v2/anime/99999999", use_cache=False)
        assert res_none is None
        # 404 确定性错误仅请求 1 次，绝不盲目退避重试 3 次
        assert fake_session.get.call_count == 1
        mock_sleep.assert_not_called()

        res_allowed = fetch_data_with_retry(
            "https://api.myanimelist.net/v2/anime/99999999",
            use_cache=False,
            allow_error_statuses={404},
        )
        assert res_allowed is fake_resp
        assert fake_session.get.call_count == 2
