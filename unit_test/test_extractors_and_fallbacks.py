# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

from main import run_cross_platform_fallbacks
from models import Anime
from src.extractors.anilist import AniListExtractor
from src.extractors.bangumi import BangumiExtractor
from src.extractors.filmarks import FilmarksExtractor
from src.extractors.myanimelist import MyAnimeListExtractor
from utils.core.global_variables import update_constants


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data


def test_bangumi_reuses_search_payload_and_blocks_non_anime_type():
    update_constants("2026年10月新番首月评分")
    extractor = BangumiExtractor()

    # 1) URL直连遇到书籍/漫画 (type=1) 必须拒绝写入
    anime_book = Anime(original_name="テスト作品", bangumi_url="https://bgm.tv/subject/999999")
    with patch.object(
        extractor,
        "_fetch_subject_data",
        return_value={"id": 999999, "type": 1, "name": "テスト作品", "date": "2026-10-01"},
    ):
        ok = extractor.extract_data(anime_book, "テスト作品")
        assert ok is False
        assert anime_book.score_bgm == "Not an anime subject"

    # 2) 搜索返回完整 date + rating 时直接消费，零额外详情 GET 请求，并精确计算 Decimal 加权分和中文译名
    anime_ok = Anime(original_name="ロメリア戦記")
    search_items = [
        {
            "id": 512345,
            "type": 2,
            "name": "ロメリア戦記",
            "name_cn": "罗梅莉亚战记",
            "date": "2026-10-04",
            "eps": 12,
            "rating": {
                "total": 100,
                "count": {"8": 55, "7": 45},  # (440 + 315) / 100 = 7.55
            },
        }
    ]
    with (
        patch.object(extractor, "_search_candidates", return_value=search_items),
        patch.object(extractor, "_fetch_subject_data") as mock_detail,
    ):
        ok = extractor.extract_by_search(anime_ok, "ロメリア戦記")
        assert ok is True
        mock_detail.assert_not_called()
        assert anime_ok.score_bgm == "7.55"
        assert anime_ok.bangumi_total == "100"
        assert anime_ok.bangumi_chinese_name == "罗梅莉亚战记"
        assert anime_ok.bangumi_subject_Date == "202610"


def test_anilist_single_query_extracts_id_mal_romaji_and_handles_null_score():
    update_constants("2026年10月新番首月评分")
    extractor = AniListExtractor()
    anime = Anime(original_name="薬屋のひとりごと 第3期（第1クール）")

    media_payload = {
        "id": 188888,
        "idMal": 60555,
        "countryOfOrigin": "JP",
        "episodes": 12,
        "season": "FALL",
        "seasonYear": 2026,
        "title": {
            "native": "薬屋のひとりごと 第3期",
            "romaji": "Kusuriya no Hitorigoto 3rd Season",
            "english": "The Apothecary Diaries Season 3",
        },
        "startDate": {"year": 2026, "month": None, "day": None},
        "averageScore": None,
        "stats": {"scoreDistribution": [{"score": 80, "amount": 30}, {"score": 90, "amount": 25}]},
        "externalLinks": [{"site": "Twitter", "url": "https://x.com/kusuriya_PR"}],
    }

    # 第1个原词返回空列表，自动回退到去括号变体 "薬屋のひとりごと 第3期" 并单次查询完成
    def fake_search(keyword, item_key=None):
        if "第1クール" in keyword:
            return []
        return [media_payload]

    with patch.object(extractor, "_search_candidates", side_effect=fake_search) as mock_search:
        ok = extractor.extract_by_search(anime, anime.original_name)
        assert ok is True
        assert mock_search.call_count == 2
        assert anime.id_mal == "60555"
        assert anime.anilist_romaji_name == "Kusuriya no Hitorigoto 3rd Season"
        assert anime.score_al == "No score found"
        assert anime.anilist_total == "55"
        assert anime.anilist_subject_Date == "202610"
        assert anime.twitter_username == "kusuriya_PR"


def test_myanimelist_404_skips_web_fallback_and_403_uses_web_fallback():
    update_constants("2026年10月新番首月评分")
    extractor = MyAnimeListExtractor()

    # 1) API 404 (not_found) 不应回退抓取网页 HTML
    anime_404 = Anime(original_name="テスト")
    with (
        patch.object(extractor, "_fetch_anime_details_with_reason", return_value=(None, "not_found")),
        patch.object(extractor, "_extract_by_web_url") as mock_web,
    ):
        ok = extractor.extract_by_identifier(anime_404, "https://myanimelist.net/anime/60555")
        assert ok is False
        mock_web.assert_not_called()
        assert anime_404.score_mal == "No results found"

    # 2) API 未配置或 403 鉴权失败时，正常回退到网页 HTML 解析
    anime_403 = Anime(original_name="テスト")
    with (
        patch.object(extractor, "_fetch_anime_details_with_reason", return_value=(None, "auth_failure")),
        patch.object(extractor, "_extract_by_web_url", return_value=True) as mock_web2,
    ):
        ok2 = extractor.extract_by_identifier(anime_403, "https://myanimelist.net/anime/60555")
        assert ok2 is True
        mock_web2.assert_called_once()


def test_filmarks_error_uses_score_fm_and_supports_quarter_and_multi_cassette_html():
    update_constants("2026年10月新番首月评分")
    extractor = FilmarksExtractor()

    # 1) 无结果时必须写入 anime.score_fm（而非旧版错误的 score_filmarks）
    anime_empty = Anime(original_name="存在しないアニメ")
    with (
        patch.object(extractor, "_fetch_api_json", return_value={"seasons": []}),
        patch("src.extractors.filmarks.fetch_data_with_retry", return_value=DummyResponse(200, text="<html></html>")),
    ):
        ok = extractor.extract_by_search(anime_empty, anime_empty.original_name)
        assert ok is False
        assert anime_empty.score_fm == "No results found"
        assert not hasattr(anime_empty, "score_filmarks")

    # 2) API 不可达时回退网页多候选 js-cassette 解析，跳过 2024 旧季并命中 2026 第2季真实链接
    html_search = """
    <html><body>
      <div class="js-cassette">
        <a href="/animes/100/201"></a>
        <h3 class="p-content-cassette__title">アオのハコ</h3>
        <div class="c-rating__score">4.1</div>
        <div data-mark='{"count": 800}'></div>
        <div class="other-info">2024年10月</div>
      </div>
      <div class="js-cassette">
        <a href="/animes/100/202"></a>
        <h3 class="p-content-cassette__title">アオのハコ Season2</h3>
        <div class="c-rating__score">4.3</div>
        <div data-mark='{"count": 120}'></div>
        <div class="other-info">2026年10月</div>
      </div>
    </body></html>
    """
    anime_web = Anime(original_name="アオのハコ Season2")
    with (
        patch.object(extractor, "_fetch_api_json", return_value=None),
        patch("src.extractors.filmarks.fetch_data_with_retry", return_value=DummyResponse(200, text=html_search)),
    ):
        ok_web = extractor.extract_by_search(anime_web, anime_web.original_name)
        assert ok_web is True
        assert anime_web.filmarks_url == "https://filmarks.com/animes/100/202"
        assert anime_web.score_fm == "4.3"
        assert anime_web.filmarks_total == "120"
        assert anime_web.filmarks_subject_Date == "202610"


def test_cross_platform_fallback_uses_id_mal_and_cross_titles():
    update_constants("2026年10月新番首月评分")
    anime = Anime(original_name="冰剣の魔術師が世界を統べるII")
    # 模拟初轮 Bangumi 命中标准日文名，AniList & MAL 未命中
    anime.bangumi_url = "https://bgm.tv/subject/500001"
    anime.bangumi_name = "氷剣の魔術師が世界を統べるII"
    anime.score_bgm = "6.50"
    anime.score_al = "No AniList results"
    anime.score_mal = "No acceptable subject found"
    anime.score_fm = "4.0"
    anime.filmarks_url = "https://filmarks.com/animes/1/2"

    def fake_extract_al(a, name):
        if "氷剣" in name:
            a.anilist_url = "https://anilist.co/anime/199999"
            a.anilist_name = "氷剣の魔術師が世界を統べるII"
            a.score_al = "72"
            a.id_mal = "61234"
            return True
        return False

    mock_mal_verified = MagicMock(
        side_effect=lambda a, mal_id: setattr(a, "myanimelist_url", f"https://myanimelist.net/anime/{mal_id}")
        or setattr(a, "score_mal", "7.12")
        or True
    )

    with (
        patch("main.extract_anilist_data", side_effect=fake_extract_al),
        patch.object(MyAnimeListExtractor, "extract_by_id_mal_verified", mock_mal_verified),
    ):
        run_cross_platform_fallbacks(anime)
        assert anime.anilist_url == "https://anilist.co/anime/199999"
        assert anime.myanimelist_url == "https://myanimelist.net/anime/61234"
        assert anime.score_mal == "7.12"
