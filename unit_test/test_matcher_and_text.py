# -*- coding: utf-8 -*-
from models import Anime
from src.data_process.matcher import (
    extract_season_and_cour,
    has_strict_mini_derivative,
    pair_similarity_and_conflict,
    score_candidate_info,
    select_best_candidate,
)
from utils.core.global_variables import (
    get_allowed_years,
    get_desired_month,
    get_desired_quarter_index,
    get_desired_year,
    update_constants,
)
from utils.date.date_processors import (
    BangumiDateProcessor,
    FilmarksDateProcessor,
    MyAnimeListDateProcessor,
)
from utils.parsers.text_processor import (
    build_query_variants,
    preprocess_name,
    sanitize_bangumi_keyword,
)


def test_update_constants_parses_year_and_month():
    update_constants("2026年10月新番首月评分")
    assert get_desired_year() == "2026"
    assert get_allowed_years() == ["2026", "2025"]
    assert get_desired_month() == 10
    assert get_desired_quarter_index() == 2026 * 4 + 3

    update_constants("2026")
    assert get_desired_year() == "2026"
    assert get_desired_month() is None
    assert get_desired_quarter_index() is None


def test_bangumi_keyword_sanitization_and_preprocess():
    # 成对连字符副标题（含紧贴汉字）与空白后前导连字符均应消除布尔 NOT 语法
    assert sanitize_bangumi_keyword("戦車椅子-TANK CHAIR-") == "戦車椅子 TANK CHAIR"
    assert (
        sanitize_bangumi_keyword("ダイヤのA actII -Second Season- 第2クール")
        == "ダイヤのA actII Second Season 第2クール"
    )
    # 词内连字符与缩写小数点必须保留
    assert preprocess_name("新テニスの王子様 U-17 WORLD CUP") == "新テニスの王子様 U-17 WORLD CUP"
    assert preprocess_name("Dr.STONE 2.5次元 らんま1/2") == "Dr.STONE 2.5次元 らんま1/2"
    assert preprocess_name("#ゾンビさがしてます") == "ゾンビさがしてます"


def test_build_query_variants_covers_cour1_and_kanji():
    v1 = build_query_variants("薬屋のひとりごと 第3期（第1クール）")
    assert "薬屋のひとりごと 第3期（第1クール）" in v1
    assert "薬屋のひとりごと 第3期" in v1

    v2 = build_query_variants("冰剣の魔術師が世界を統べるII")
    assert "氷剣の魔術師が世界を統べるII" in v2

    v3 = build_query_variants("Battle Spirits [Re] 絶界の空")
    assert "Battle Spirits Re 絶界の空" in v3

    v4 = build_query_variants("ダイヤのA actII -Second Season- 第2クール")
    assert "ダイヤのA actⅡ Second Season 第2クール" in v4


def test_extract_season_and_cour_rich_patterns():
    assert extract_season_and_cour(["ブラッククローバー 2nd Season"]) == (2, None)
    assert extract_season_and_cour(["ブラッククローバー Second Season"]) == (2, None)
    assert extract_season_and_cour(["転生したら剣でしたII"]) == (2, None)
    assert extract_season_and_cour(["サイバーパンク: エッジランナーズ２"]) == (2, None)
    assert extract_season_and_cour(["帰還者の魔法は特別です 第二期"]) == (2, None)
    assert extract_season_and_cour(["夜桜さんちの大作戦 第2期 第2クール"]) == (2, 2)
    assert extract_season_and_cour(["薬屋のひとりごと 第3期（第1クール）"]) == (3, 1)
    assert extract_season_and_cour(
        ["スティール・ボール・ラン ジョジョの奇妙な冒険 2nd STAGE&3rd STAGE"]
    ) == (None, 3)


def test_mini_derivative_guard_vs_normal_katakana_and_special():
    assert has_strict_mini_derivative(["転生したらスライムだった件 ミニアニメ"]) is True
    assert has_strict_mini_derivative(["ぷちアニメ 特典"]) is True
    assert has_strict_mini_derivative(["総集編"]) is True
    # 含 ミニ 子串的正常外来语不得误判
    assert has_strict_mini_derivative(["ジェミニの騎士", "ミニマリストの冒険"]) is False
    # 特別篇不列入硬排除，确保独立收录的特别篇正常命中
    assert has_strict_mini_derivative(["わたしの幸せな結婚 特別篇"]) is False


def test_word_order_swap_and_cross_installment_similarity():
    sim1, conf1 = pair_similarity_and_conflict("戦車椅子-TANK CHAIR-", "TANK CHAIR-戦車椅子-")
    assert conf1 == ""
    assert sim1 >= 0.95

    sim2, conf2 = pair_similarity_and_conflict(
        "スティール・ボール・ラン ジョジョの奇妙な冒険 2nd STAGE&3rd STAGE",
        "ジョジョの奇妙な冒険 スティール・ボール・ラン 2nd STAGE",
    )
    assert conf2 == ""
    assert sim2 >= 0.80

    # 与 1st STAGE 对比必须识别为明确クール冲突
    _, conf_clash = pair_similarity_and_conflict(
        "スティール・ボール・ラン ジョジョの奇妙な冒険 2nd STAGE&3rd STAGE",
        "スティール・ボール・ラン ジョジョの奇妙な冒険 1st STAGE",
    )
    assert conf_clash.startswith("explicit_cour_mismatch")

    sim3, conf3 = pair_similarity_and_conflict("作品名 第2期", "作品名 第2クール")
    assert conf3 == ""
    assert sim3 >= 0.95


def test_select_best_candidate_blocks_wrong_season_and_ranks_target_year_first():
    update_constants("2026年10月新番首月评分")
    anime = Anime(original_name="アオのハコ Season2")

    candidates = [
        # 第1顺位是 2025 年无季数第 1 季 -> 应被窄黑名单硬拦截
        {
            "id": "1001",
            "name": "アオのハコ",
            "titles": ["アオのハコ", "Ao no Hako"],
            "year": "2025",
            "date": "202501",
        },
        # 第2顺位是明確错季 3rd Season -> 硬拦截
        {
            "id": "1003",
            "name": "アオのハコ 3rd Season",
            "titles": ["アオのハコ 3rd Season"],
            "year": "2026",
            "date": "202610",
        },
        # 第3顺位是正确的 2026 年第 2 季 -> 命中
        {
            "id": "1002",
            "name": "アオのハコ 第2期",
            "titles": ["アオのハコ 第2期", "Ao no Hako Season 2"],
            "year": "2026",
            "date": "202610",
        },
    ]

    chosen = select_best_candidate(
        candidates=candidates,
        extract_candidate_info=lambda c: c,
        platform_name="Bangumi",
        platform_key="bgm",
        anime=anime,
        query=anime.original_name,
    )
    assert chosen is not None
    assert chosen["id"] == "1002"


def test_romaji_only_candidate_preserved_while_same_script_noise_rejected():
    update_constants("2026年10月新番首月评分")

    # 1) 日文原名搜出仅含纯罗马音标题的 2026 候选 -> 高召回策略必须保留，不误杀
    anime_romaji = Anime(original_name="ロメリア戦記")
    romaji_cand = {
        "id": "2001",
        "name": "Romelia Senki",
        "titles": ["Romelia Senki"],
        "year": "2026",
        "date": "202610",
    }
    chosen_romaji = select_best_candidate(
        candidates=[romaji_cand],
        extract_candidate_info=lambda c: c,
        platform_name="MyAnimeList",
        platform_key="mal",
        anime=anime_romaji,
        query=anime_romaji.original_name,
    )
    assert chosen_romaji is not None
    assert chosen_romaji["id"] == "2001"

    # 2) 同为日文但仅撞上“特別”两字的无关作品 -> 同语种底线拦截
    anime_special = Anime(original_name="わたしの幸せな結婚 特別篇")
    unrelated_cand = {
        "id": "3001",
        "name": "シンカリオン チェンジ ザ ワールド 特別ダイヤ版",
        "titles": ["シンカリオン チェンジ ザ ワールド 特別ダイヤ版"],
        "year": "2026",
        "date": "202604",
    }
    chosen_noise = select_best_candidate(
        candidates=[unrelated_cand],
        extract_candidate_info=lambda c: c,
        platform_name="Filmarks",
        platform_key="fm",
        anime=anime_special,
        query=anime_special.original_name,
    )
    assert chosen_noise is None


def test_same_year_subtitle_sequel_is_kept_when_query_has_season2():
    update_constants("2026年10月新番首月评分")
    anime = Anime(original_name="とある作品 Season2")
    subtitle_sequel = {
        "id": "4001",
        "name": "とある作品 覚醒篇",
        "titles": ["とある作品 覚醒篇"],
        "year": "2026",
        "date": "202610",
    }
    scored = score_candidate_info(
        subtitle_sequel, anime=anime, query=anime.original_name, platform_key="bgm"
    )
    assert scored.hard_blocked is False


def test_date_processors_handle_quarter_and_partial_dates():
    assert MyAnimeListDateProcessor.parse("Oct 5, 2026 to ?") == "202610"
    assert MyAnimeListDateProcessor.parse("Oct 2026") == "202610"
    assert MyAnimeListDateProcessor.parse("Oct, 2026") == "202610"
    assert MyAnimeListDateProcessor.parse("Fall 2026") == "202610"
    assert MyAnimeListDateProcessor.parse("2026 to ?") == "2026"

    assert BangumiDateProcessor.parse("2026-10-03") == "202610"
    assert BangumiDateProcessor.parse("2026年10月") == "202610"
    assert BangumiDateProcessor.parse("2026年秋") == "202610"
    assert BangumiDateProcessor.parse("2026年予定") == "2026"

    assert FilmarksDateProcessor.parse("2026-Q4") == "202610"
    assert FilmarksDateProcessor.parse("2026年10月4日") == "202610"
    assert FilmarksDateProcessor.parse("2026年秋") == "202610"
