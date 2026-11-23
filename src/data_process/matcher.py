# src/data_process/matcher.py
# 高召回结构化候选排序择优与窄黑名单冲突排除引擎
# 结合 anime-score-aggregator 的结构化季数/クール/衍生词解析能力，适配 mzzbscore 无人工审核池的自动填表场景：
# - 多候选综合打分排序择优（取代“撞见第一个年份合规就停”）
# - 窄黑名单仅排除 100% 明确的错季/衍生ミニ短篇，不设高字面相似度拒收门槛，确保不掉召回率

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from utils.core.global_variables import (
    get_allowed_years,
    get_desired_quarter_index,
    get_desired_year,
)

# 提前短路阈值：第 1 顺位命中目标年份（且若有目标季度也吻合）、无任何冲突且近乎满分时提前结束，省去多余详情请求
EARLY_STOP_CONFIDENCE = 0.96

# 仅用于模糊搜索兜底通道（如 MAL API /v2/anime?q=）的最低相关性要求
FUZZY_CHANNEL_MIN_SIMILARITY = 0.45
# 同语种文字（双方均含日文假名/汉字）时的极低底线，仅拦截完全无关的单词撞车（如搜"わたしの幸せな結婚 特別篇"撞上"シンカリオン 特別ダイヤ版" sim=0.16）；
# 当一方为日文而另一方仅有罗马音/英文时跳过此检查，确保纯罗马音条目 100% 不掉召回！
SAME_SCRIPT_FLOOR_SIMILARITY = 0.34

_TIME_BONUS_EXACT = Decimal("0.20")
_TIME_BONUS_SAME_QUARTER = Decimal("0.18")
_TIME_BONUS_ADJ_QUARTER = Decimal("0.12")
_TIME_BONUS_DESIRED_YEAR = Decimal("0.16")
_TIME_BONUS_ALLOWED_PREV_YEAR = Decimal("0.06")

_WEIGHTS_WITH_ID_CROSS = (Decimal("0.72"), Decimal("0.18"), Decimal("0.10"))
_WEIGHTS_DEFAULT = (Decimal("0.80"), Decimal("0.20"), Decimal("0.00"))

_QUARTER_TEXT_RE = re.compile(r"^(\d{4})-Q([1-4])", re.IGNORECASE)
_YYYYMM_RE = re.compile(r"^(\d{4})(0[1-9]|1[0-2])$")

# ---------------------------------------------------------------------------
# 结构化标题清洗、季数/分部提取与衍生短篇互斥正则
# ---------------------------------------------------------------------------
_YEAR_DISAMBIG_RE = re.compile(r"\s*[\(（]\s*(?:19|20)\d{2}\s*[\)）]")
_DISAMBIG_SUFFIX_RE = re.compile(
    r"\s*[\(（]\s*(?:tv|tv\s*series|ona|ova|oad|movie|special|アニメ|新アニメ)\s*[\)）]\s*$",
    re.IGNORECASE,
)

_KANJI_NUM_MAP = {
    "一": 1,
    "二": 2,
    "弐": 2,
    "三": 3,
    "参": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_ROMAN_NUM_MAP = {
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "ⅱ": 2,
    "ⅲ": 3,
    "ⅳ": 4,
    "ⅴ": 5,
    "ⅵ": 6,
}
_WORD_ORDINAL_MAP = {
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "セカンド": 2,
    "サード": 3,
    "フォース": 4,
}

_EXPLICIT_SEASON_PATTERNS = (
    re.compile(
        r"(?:第\s*)?([1-9一二弐三参四肆五六七八九])\s*(?:期|シーズン|シリーズ|幕)",
        re.IGNORECASE,
    ),
    re.compile(r"第\s*([1-9一二弐三参四肆五六七八九])\s*章"),
    re.compile(r"([二弐三参四肆五六])\s*ノ\s*章"),
    re.compile(
        r"(?<![a-z0-9])([1-9])\s*(?:st|nd|rd|th)\s+season(?![a-z0-9])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![a-z0-9])(second|third|fourth|fifth)\s+season(?![a-z0-9])",
        re.IGNORECASE,
    ),
    re.compile(r"(セカンド|サード|フォース)\s*シーズン"),
    re.compile(r"(?<![a-z0-9])season\s*([1-9])(?![0-9])", re.IGNORECASE),
    re.compile(
        r"(?<![a-z0-9])act\.?\s*([2-9]|ii|iii|iv|ⅱ|ⅲ|ⅳ)(?![a-z0-9])",
        re.IGNORECASE,
    ),
)
_ROMAN_SEASON_RE = re.compile(
    r"(?:(?<=[\s:：\-〜～])|(?<=[\u3040-\u30ff\u3400-\u9fff]))"
    r"(iii|ii|iv|vi|v)(?=$|[\s:：\-〜～!！?？])",
    re.IGNORECASE,
)
_TRAILING_DIGIT_SEASON_RE = re.compile(
    r"(?:(?<=[\u3040-\u30ff\u3400-\u9fff\s。！!？?])(?<![a-zA-Z0-9_/.]))([2-6弐参])\s*$"
)

_COUR_PART_PATTERNS = (
    re.compile(r"(?:第\s*)?([1-9])\s*(?:st|nd|rd|th)?\s*クール", re.IGNORECASE),
    re.compile(r"(後半|後編)\s*クール"),
    re.compile(r"(?<![a-z0-9])part\.?\s*([1-9]|ii|iii)(?![a-z0-9])", re.IGNORECASE),
    re.compile(
        r"(?<![a-z0-9])([1-9])\s*(?:st|nd|rd|th)?\s*stage(?![a-z0-9])",
        re.IGNORECASE,
    ),
    re.compile(r"パート\s*([1-9])"),
    re.compile(r"第\s*([1-9一二三四])\s*(?:部|部分)"),
)

_REDUNDANT_S1_RE = re.compile(
    r"(?:(?:第\s*)?[1一]\s*(?:st\s*)?(?:期|シーズン)"
    r"|(?<![a-z0-9])1st\s+season(?![a-z0-9])"
    r"|(?<![a-z0-9])first\s+season(?![a-z0-9])"
    r"|(?<![a-z0-9])season\s*1(?![0-9]))",
    re.IGNORECASE,
)
_REDUNDANT_C1_RE = re.compile(
    r"(?:[\(（\[]?\s*(?:第\s*)?[1一]\s*(?:st\s*)?(?:クール|部|部分)\s*[\)）\]]?"
    r"|(?<![a-z0-9])part\.?\s*1(?![0-9])"
    r"|(?<![a-z0-9])1st\s+stage(?![a-z0-9])"
    r"|パート\s*1(?![0-9]))",
    re.IGNORECASE,
)

# 严格ミニ短篇/总集篇/PV标记（正片搜到此类条目时硬排除；注意不含 "特別編/特別篇"，因为特别篇常作为独立条目收录）
_STRICT_MINI_DERIVATIVE_PATTERNS = (
    re.compile(
        r"ミニアニメ|ミニ劇場|ミニドラマ|まめアニメ|ぷちアニメ|ちびアニメ|ピクチャードラマ|マナー映像"
    ),
    re.compile(r"(?<![ァ-ヴー])(?:ミニ|ぷち|プチ)(?![ァ-ヴー])"),
    re.compile(r"(?:[\s　\-〜～:：]|^)(?:みに|ちび)(?:[\s　\-〜～:：!！]|$)"),
    re.compile(r"(?<![a-z])(?:mini|petit|chibi|recap|pv|cm)(?![a-z])", re.IGNORECASE),
    re.compile(r"総集編|ダイジェスト|picture\s*drama", re.IGNORECASE),
)
# 软性特别篇标记（仅作小幅排序区分，绝不硬拦截，保证 "わたしの幸せな結婚 特別篇" 等正常命中）
_SPECIAL_EPISODE_RE = re.compile(
    r"特別[編篇]|プロローグ|(?<![a-z])prologue(?![a-z])|web\s*特別|web\s*special",
    re.IGNORECASE,
)

_TILDE_SUBTITLE_RE = re.compile(r"^(.{4,}?)\s*[〜～](.{8,}?)[〜～]?\s*$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


def clean_disambig(raw: str) -> str:
    """剥离年份消歧括号 (YYYY) 与末尾制式标签 (TV)/(ONA)/(OVA)"""
    text = unicodedata.normalize("NFKC", str(raw or "")).strip()
    text = _YEAR_DISAMBIG_RE.sub(" ", text)
    text = _DISAMBIG_SUFFIX_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(value: Optional[str]) -> str:
    """基础归一化标题（NFKC + 去消歧括号 + 小写化 + 去空白标点）"""
    if not value:
        return ""
    text = clean_disambig(str(value)).lower()
    return re.sub(
        r"[\s\-_~:：;；,，、。.!！?？'\"“”‘’\[\]【】()（）<>〈〉《》「」『』/\\|・･☆★♪…·〜～&#]",
        "",
        text,
    )


def _to_int_season(token: str) -> Optional[int]:
    raw_trimmed = str(token or "").strip()
    if raw_trimmed in _WORD_ORDINAL_MAP:
        return _WORD_ORDINAL_MAP[raw_trimmed]
    t = unicodedata.normalize("NFKC", raw_trimmed).strip().lower()
    if t in ("後半", "後編"):
        return 2
    if t.isdigit():
        return int(t)
    if t in _KANJI_NUM_MAP:
        return _KANJI_NUM_MAP[t]
    if t in _ROMAN_NUM_MAP:
        return _ROMAN_NUM_MAP[t]
    if t in _WORD_ORDINAL_MAP:
        return _WORD_ORDINAL_MAP[t]
    return None


def extract_season_and_cour_sets(titles: Sequence[str]) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """从标题序列中提取所有明确的 (seasons_tuple, cours_tuple)，兼容 '2nd STAGE&3rd STAGE' 等合集表述"""
    seasons_found: List[int] = []
    cours_found: List[int] = []

    for raw in titles:
        if not raw:
            continue
        cleaned = clean_disambig(raw)
        without_cour = cleaned

        for pat in _COUR_PART_PATTERNS:
            for m_c in pat.finditer(cleaned):
                c_val = _to_int_season(m_c.group(1))
                if c_val and c_val not in cours_found:
                    cours_found.append(c_val)
            without_cour = pat.sub(" ", without_cour)

        for pat in _EXPLICIT_SEASON_PATTERNS:
            for m_s in pat.finditer(without_cour):
                s_val = _to_int_season(m_s.group(1))
                if s_val and s_val not in seasons_found:
                    seasons_found.append(s_val)

    if not seasons_found:
        for raw in titles:
            if not raw:
                continue
            without_cour = clean_disambig(raw)
            for pat in _COUR_PART_PATTERNS:
                without_cour = pat.sub(" ", without_cour)
            without_cour = without_cour.strip()

            m_r = _ROMAN_SEASON_RE.search(without_cour)
            if m_r:
                s_val = _to_int_season(m_r.group(1))
                if s_val:
                    seasons_found.append(s_val)
                    break
            m_d = _TRAILING_DIGIT_SEASON_RE.search(without_cour)
            if m_d:
                s_val = _to_int_season(m_d.group(1))
                if s_val:
                    seasons_found.append(s_val)
                    break

    return tuple(sorted(seasons_found)), tuple(sorted(cours_found))


def extract_season_and_cour(titles: Sequence[str]) -> Tuple[Optional[int], Optional[int]]:
    """从标题序列中提取最明确的 (season_num, cour_or_part_num)"""
    seasons, cours = extract_season_and_cour_sets(titles)
    return (seasons[-1] if seasons else None), (cours[-1] if cours else None)


def has_strict_mini_derivative(titles: Sequence[str]) -> bool:
    """检测是否包含ミニアニメ/ぷち/総集編/PV等衍生短篇标记"""
    for raw in titles:
        if not raw:
            continue
        text = unicodedata.normalize("NFKC", str(raw))
        if any(pat.search(text) for pat in _STRICT_MINI_DERIVATIVE_PATTERNS):
            return True
    return False


def has_special_marker(titles: Sequence[str]) -> bool:
    """检测是否包含特別編/特別篇/Prologue标记"""
    for raw in titles:
        if not raw:
            continue
        text = unicodedata.normalize("NFKC", str(raw))
        if _SPECIAL_EPISODE_RE.search(text):
            return True
    return False


def normalize_for_compare(
    raw: Optional[str],
    *,
    strip_s1: bool = False,
    strip_c1: bool = False,
    canonical_season: Optional[int] = None,
    canonical_cour: Optional[int] = None,
) -> str:
    """结构化归一化：支持剥离冗余第1期/第1クール及同季数/同クール跨语法统一"""
    if not raw:
        return ""
    text = clean_disambig(str(raw))
    if strip_c1:
        text = _REDUNDANT_C1_RE.sub("", text)
    if strip_s1:
        text = _REDUNDANT_S1_RE.sub("", text)
    if canonical_cour is not None and canonical_cour >= 2:
        for pat in _COUR_PART_PATTERNS:
            if pat.search(text):
                text = pat.sub(f" c{canonical_cour} ", text, count=1)
                break
    if canonical_season is not None and canonical_season >= 2:
        replaced = False
        for pat in _EXPLICIT_SEASON_PATTERNS:
            if pat.search(text):
                text = pat.sub(f" s{canonical_season} ", text, count=1)
                replaced = True
                break
        if not replaced:
            for pat in _COUR_PART_PATTERNS:
                if pat.search(text):
                    text = pat.sub(f" s{canonical_season} ", text, count=1)
                    replaced = True
                    break
        if not replaced:
            if _ROMAN_SEASON_RE.search(text):
                text = _ROMAN_SEASON_RE.sub(f" s{canonical_season} ", text, count=1)
            elif _TRAILING_DIGIT_SEASON_RE.search(text):
                text = _TRAILING_DIGIT_SEASON_RE.sub(f" s{canonical_season} ", text, count=1)
    return normalize_title(text)


def pair_similarity_and_conflict(a: Optional[str], b: Optional[str]) -> Tuple[float, str]:
    """
    计算单对标题的结构化相似度与冲突类型：
    - explicit_season_mismatch: 双方均明确标了不同季数（如 3rd season vs 2nd season）
    - implicit_season_mismatch_req_sequel: 查询要求第2季+，候选无季数标记（可能是第1季或改了副标题的新季）
    - implicit_season_mismatch_cand_sequel: 查询无季数标记，候选明确标了第2季+
    - explicit_cour_mismatch: 双方均明确标了不同クール/Part（如 第2クール vs 第1クール）
    - implicit_cour_mismatch: 一方标了第2クール+，另一方无クール标记
    """
    if not a or not b:
        return 0.0, ""
    r_seasons, r_cours = extract_season_and_cour_sets((a,))
    c_seasons, c_cours = extract_season_and_cour_sets((b,))
    r_s = r_seasons[-1] if r_seasons else None
    r_c = r_cours[-1] if r_cours else None
    c_s = c_seasons[-1] if c_seasons else None
    c_c = c_cours[-1] if c_cours else None
    eff_r_s = r_s or 1
    eff_r_c = r_c or 1
    eff_c_s = c_s or 1
    eff_c_c = c_c or 1

    seasons_overlap = bool(r_seasons and c_seasons and (set(r_seasons) & set(c_seasons)))
    cours_overlap = bool(r_cours and c_cours and (set(r_cours) & set(c_cours)))

    # 跨站常见等价：一方标 "第2期 / Season 2" (season=N, cour=None)，另一方标 "第2クール / Part 2" (season=None, cour=N)
    cross_installment_eq = (
        r_s is not None and r_s >= 2 and not r_cours and c_s is None and (r_s in c_cours)
    ) or (c_s is not None and c_s >= 2 and not c_cours and r_s is None and (c_s in r_cours))

    pair_conflict = ""
    if not cross_installment_eq:
        if r_seasons and c_seasons and not seasons_overlap:
            pair_conflict = f"explicit_season_mismatch:{r_s}vs{c_s}"
        elif r_s is not None and r_s >= 2 and c_s is None:
            pair_conflict = f"implicit_season_mismatch_req_sequel:{r_s}vs1"
        elif r_s is None and c_s is not None and c_s >= 2:
            pair_conflict = f"implicit_season_mismatch_cand_sequel:1vs{c_s}"
        elif r_cours and c_cours and not cours_overlap:
            pair_conflict = f"explicit_cour_mismatch:{r_c}vs{c_c}"
        elif ((r_c or 1) >= 2 or (c_c or 1) >= 2) and not cours_overlap and eff_r_c != eff_c_c:
            pair_conflict = f"implicit_cour_mismatch:{eff_r_c}vs{eff_c_c}"

    strip_s1 = eff_r_s == 1 and eff_c_s == 1
    strip_c1 = eff_r_c == 1 and eff_c_c == 1
    if cross_installment_eq:
        canon_s = r_s or c_s
        canon_c = None
    else:
        shared_s = sorted(set(r_seasons) & set(c_seasons))
        shared_c = sorted(set(r_cours) & set(c_cours))
        canon_s = shared_s[-1] if (shared_s and shared_s[-1] >= 2) else None
        canon_c = shared_c[-1] if (shared_c and shared_c[-1] >= 2) else None

    na = normalize_for_compare(
        a,
        strip_s1=strip_s1,
        strip_c1=strip_c1,
        canonical_season=canon_s,
        canonical_cour=canon_c,
    )
    nb = normalize_for_compare(
        b,
        strip_s1=strip_s1,
        strip_c1=strip_c1,
        canonical_season=canon_s,
        canonical_cour=canon_c,
    )
    if not na or not nb:
        return 0.0, ""
    if na == nb:
        sim = 1.0
    elif sorted(na) == sorted(nb) and len(na) >= 4:
        # 词序颠倒但字符完全一致（如 "戦車椅子-TANK CHAIR-" vs "TANK CHAIR-戦車椅子-"）
        sim = 0.98
    else:
        sim = SequenceMatcher(None, na, nb).ratio()
        # 词块顺序对调补偿（注意不按中黑点 "・" 切分，保持片假名复合词如 "スティール・ボール・ラン" 完整）
        tokens_a = [
            normalize_title(tok)
            for tok in re.split(r"[\s\-_~:：/&＆〜～]+", clean_disambig(str(a)))
            if normalize_title(tok)
        ]
        tokens_b = [
            normalize_title(tok)
            for tok in re.split(r"[\s\-_~:：/&＆〜～]+", clean_disambig(str(b)))
            if normalize_title(tok)
        ]
        if len(tokens_a) >= 2 and len(tokens_b) >= 2:
            reordered_sim = SequenceMatcher(
                None, "".join(sorted(tokens_a)), "".join(sorted(tokens_b))
            ).ratio()
            if reordered_sim > sim:
                sim = max(sim, reordered_sim * 0.97)
        # 无硬冲突时的前缀/主副标题包含补偿（如 "ようこそ実力至上主義の教室へ 4th Season" vs "... 4th Season 2年生編1学期"）
        if not pair_conflict and min(len(na), len(nb)) >= 5:
            shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
            if longer.startswith(shorter) or shorter in longer:
                contain_sim = max(0.76, 0.92 - min(len(longer) - len(shorter), 20) * 0.008)
                sim = max(sim, contain_sim)
    return sim, pair_conflict


def best_similarity_with_conflict(
    references: Iterable[str],
    titles: Sequence[str],
) -> Tuple[float, str]:
    """在多组参考标题 × 候选标题中选取最优对，优先选择无季数冲突的高匹配对"""
    best_clean_sim = -1.0
    best_any_sim = 0.0
    best_pair_conflict = ""

    for ref in references:
        if not ref:
            continue
        for title in titles:
            if not title:
                continue
            sim, pair_conf = pair_similarity_and_conflict(ref, title)
            if not pair_conf and sim > best_clean_sim:
                best_clean_sim = sim
            if sim > best_any_sim or (sim == best_any_sim and not pair_conf):
                best_any_sim = sim
                best_pair_conflict = pair_conf

    if best_clean_sim >= 0.72 or (best_clean_sim >= best_any_sim - 0.08 and best_clean_sim > 0):
        return best_clean_sim, ""
    return best_any_sim, best_pair_conflict


def _maybe_apply_tilde_subtitle_floor(
    sim: float,
    *,
    references: Sequence[str],
    cand_titles: Sequence[str],
    has_conflicts: bool,
    time_aligned: bool,
) -> float:
    """无冲突且时间吻合时，对波浪号长副标题包含关系给予 0.85 相似度保底"""
    if has_conflicts or sim >= 0.85 or not time_aligned:
        return sim
    for rt in references:
        for ct in cand_titles:
            m_a = _TILDE_SUBTITLE_RE.match(unicodedata.normalize("NFKC", rt))
            m_c = _TILDE_SUBTITLE_RE.match(unicodedata.normalize("NFKC", ct))
            if m_a and not m_c:
                if normalize_for_compare(m_a.group(1), strip_s1=True, strip_c1=True) == normalize_for_compare(
                    ct, strip_s1=True, strip_c1=True
                ):
                    return max(sim, 0.85)
            elif m_c and not m_a:
                if normalize_for_compare(m_c.group(1), strip_s1=True, strip_c1=True) == normalize_for_compare(
                    rt, strip_s1=True, strip_c1=True
                ):
                    return max(sim, 0.85)
    return sim


def parse_exact_iso_date(raw: Optional[str]) -> Optional[date]:
    """解析精确到日的 ISO 日期 YYYY-MM-DD"""
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if len(text) < 10 or "-Q" in text.upper():
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_quarter_index(date_or_yyyymm: Optional[str]) -> Optional[int]:
    """从 YYYY-MM-DD、YYYY-Qn 或 YYYYMM 中计算季度序号 (year * 4 + quarter_0_to_3)"""
    if not date_or_yyyymm:
        return None
    text = str(date_or_yyyymm).strip()
    m_q = _QUARTER_TEXT_RE.match(text)
    if m_q:
        return int(m_q.group(1)) * 4 + int(m_q.group(2)) - 1
    m_ym = _YYYYMM_RE.match(text)
    if m_ym:
        return int(m_ym.group(1)) * 4 + (int(m_ym.group(2)) - 1) // 3
    if len(text) >= 7 and text[4] == "-":
        try:
            year = int(text[:4])
            month = int(text[5:7])
            if 1 <= month <= 12:
                return year * 4 + (month - 1) // 3
        except ValueError:
            return None
    return None


def _is_likely_chinese_only_query(text: Optional[str]) -> bool:
    if not text:
        return False
    return bool(_CJK_RE.search(text)) and not bool(_KANA_RE.search(text))


def collect_reference_titles(anime: Any, extra_query: Optional[str] = None) -> Tuple[str, ...]:
    """从 Anime 实例与当前搜索词收集可信参考标题（去重，排除错误占位符）"""
    invalid = {"", "No name found", "未知名称", None}
    raw_titles = []
    if anime is not None:
        raw_titles.extend(
            [
                getattr(anime, "original_name", ""),
                getattr(anime, "anilist_japanese_name", ""),
                getattr(anime, "anilist_romaji_name", ""),
                getattr(anime, "anilist_english_name", ""),
                getattr(anime, "myanimelist_japanese_name", ""),
                getattr(anime, "myanimelist_english_name", ""),
            ]
        )
    if extra_query:
        raw_titles.append(extra_query)

    result: List[str] = []
    seen = set()
    for t in raw_titles:
        if t in invalid or not str(t).strip():
            continue
        text = str(t).strip()
        norm = normalize_title(text)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(text)
    return tuple(result)


def resolve_reference_quarter(anime: Any) -> Optional[int]:
    """优先使用表头指定的目标季度，其次使用已匹配平台的共识季度"""
    desired_q = get_desired_quarter_index()
    if desired_q is not None:
        return desired_q
    if anime is None:
        return None

    quarters: List[int] = []
    for attr in (
        "anilist_subject_Date",
        "filmarks_subject_Date",
        "myanimelist_subject_Date",
        "bangumi_subject_Date",
    ):
        q = parse_quarter_index(getattr(anime, attr, None))
        if q is not None:
            quarters.append(q)
    if not quarters:
        return None
    return max(set(quarters), key=quarters.count)


@dataclass
class ScoredCandidateResult:
    candidate_info: Dict[str, Any]
    confidence: float
    similarity: float
    id_cross: bool = False
    hard_blocked: bool = False
    block_reason: str = ""
    soft_conflicts: Tuple[str, ...] = field(default_factory=tuple)
    index: int = 0


def score_candidate_info(
    candidate_info: Dict[str, Any],
    *,
    anime: Any = None,
    query: Optional[str] = None,
    platform_key: str = "",
) -> ScoredCandidateResult:
    """
    评估单个候选条目的排序置信度，并按“窄黑名单”原则判定是否存在 100% 明确的错绑硬冲突：
    硬排除条件（仅限以下明确错误）：
      1. 正片搜到了 ミニアニメ / ぷちアニメ / 総集編 / PV / CM 等迷你衍生短篇
      2. 标题明确写了不同季数（如 3rd season vs 2nd season）
      3. 标题明确写了不同クール（如 第2クール vs 第1クール）
      4. 查询明确要求第 2 季+，而候选无任何季数标记 **且** 放送年份并非目标年（即前一年播出的第 1 季）
      5. 查询无季数标记且非目标年续作，而候选明确是前一年不同季条目（若在目标年仅做排序降权，不硬拦）
    其余情况一律保留参选资格，通过综合分高低排序择优！
    """
    refs = collect_reference_titles(anime, extra_query=query)
    raw_titles = list(candidate_info.get("titles") or [])
    if not raw_titles and candidate_info.get("name"):
        raw_titles.append(candidate_info["name"])

    title_zh = candidate_info.get("title_zh")
    if title_zh and any(_is_likely_chinese_only_query(r) for r in refs):
        raw_titles.append(title_zh)

    cand_titles = tuple(str(t).strip() for t in raw_titles if t and str(t).strip())
    if not refs or not cand_titles:
        return ScoredCandidateResult(candidate_info=candidate_info, confidence=0.0, similarity=0.0)

    desired_year = get_desired_year()
    allowed_years = get_allowed_years()
    cand_year = str(candidate_info.get("year") or "")
    cand_release = candidate_info.get("release_date") or candidate_info.get("date")
    cand_quarter = parse_quarter_index(cand_release) or parse_quarter_index(candidate_info.get("date"))
    ref_quarter = resolve_reference_quarter(anime)

    # 外部 ID 交叉（AniList idMal -> MyAnimeList）
    anime_id_mal = str(getattr(anime, "id_mal", "") or "").strip() if anime is not None else ""
    cand_id = str(candidate_info.get("id") or "").strip()
    has_id_cross_slot = platform_key in ("mal", "myanimelist") and bool(anime_id_mal)
    id_cross = has_id_cross_slot and cand_id == anime_id_mal

    w_title, _w_time, w_id = (
        _WEIGHTS_WITH_ID_CROSS if has_id_cross_slot else _WEIGHTS_DEFAULT
    )

    soft_conflicts: List[str] = []
    hard_blocked = False
    block_reason = ""

    # 1. 正片 vs 迷你短篇/总集篇/PV 硬排除（特别篇 特別編/特別篇 不硬拦）
    ref_is_mini = has_strict_mini_derivative(refs)
    cand_is_mini = has_strict_mini_derivative(cand_titles)
    if not ref_is_mini and cand_is_mini:
        hard_blocked = True
        block_reason = "mini_or_recap_derivative"

    if has_special_marker(refs) != has_special_marker(cand_titles):
        soft_conflicts.append("special_marker_diff")

    sim, pair_conflict = best_similarity_with_conflict(refs, cand_titles)
    if pair_conflict and not hard_blocked:
        if pair_conflict.startswith("explicit_season_mismatch") or pair_conflict.startswith(
            "explicit_cour_mismatch"
        ):
            # 双方明确写出不同季数/不同クール（如 3rd season vs 2nd season）：硬排除
            hard_blocked = True
            block_reason = pair_conflict
        elif pair_conflict.startswith("implicit_season_mismatch_req_sequel"):
            # 原名明确要求第2季+，候选无季数数字：
            # - 若候选是前一年（如 2025）的老条目 -> 必为上一季/第1季，硬排除！
            # - 若候选就是目标年（如 2026） -> 可能是改用新副标题的续作（如 "〇〇篇"），仅降权不硬排除！
            if desired_year and cand_year and cand_year != desired_year:
                hard_blocked = True
                block_reason = f"{pair_conflict}(year={cand_year})"
            else:
                soft_conflicts.append(pair_conflict)
        elif pair_conflict.startswith("implicit_cour_mismatch"):
            # 连续两クール作品在 Bangumi 等平台常合并为单个条目（无第2クール独立条目），
            # 因此仅记为软冲突降权：若平台存在独立的第2クール条目会自动高分胜出，若仅合并条目也能保住召回！
            soft_conflicts.append(pair_conflict)
        else:
            soft_conflicts.append(pair_conflict)

    # 非 JP 动画轻微排序降权（不硬拦，保证偶尔录入国创/韩漫改也能正常搜到，但同名时优先日本动画）
    country = candidate_info.get("country_of_origin")
    if country and country != "JP":
        soft_conflicts.append(f"non_jp:{country}")

    # 时间梯度加分
    anime_exact = (
        parse_exact_iso_date(getattr(anime, "exact_start_date", None)) if anime is not None else None
    )
    cand_exact = parse_exact_iso_date(candidate_info.get("release_date"))

    time_bonus = Decimal("0")
    time_aligned = False
    if (
        anime_exact is not None
        and cand_exact is not None
        and abs((anime_exact - cand_exact).days) <= 14
    ):
        time_bonus = _TIME_BONUS_EXACT
        time_aligned = True
    elif ref_quarter is not None and cand_quarter is not None:
        q_diff = abs(ref_quarter - cand_quarter)
        if q_diff == 0:
            time_bonus = _TIME_BONUS_SAME_QUARTER
            time_aligned = True
        elif q_diff == 1:
            time_bonus = _TIME_BONUS_ADJ_QUARTER
            time_aligned = True
        elif desired_year and cand_year == desired_year:
            time_bonus = Decimal("0.08")
            time_aligned = True
    elif desired_year and cand_year == desired_year:
        time_bonus = _TIME_BONUS_DESIRED_YEAR
        time_aligned = True
    elif allowed_years and cand_year in allowed_years:
        time_bonus = _TIME_BONUS_ALLOWED_PREV_YEAR
        time_aligned = True

    sim = _maybe_apply_tilde_subtitle_floor(
        sim,
        references=refs,
        cand_titles=cand_titles,
        has_conflicts=bool(hard_blocked or soft_conflicts),
        time_aligned=time_aligned,
    )

    penalty = Decimal("0")
    for sc in soft_conflicts:
        if sc.startswith("implicit_cour"):
            penalty += Decimal("0.16")
        elif sc.startswith("implicit_season"):
            penalty += Decimal("0.12")
        elif sc == "special_marker_diff":
            penalty += Decimal("0.08")
        elif sc.startswith("non_jp"):
            penalty += Decimal("0.05")

    raw_score = (
        w_title * Decimal(str(sim))
        + time_bonus
        + (w_id if id_cross else Decimal("0"))
        - penalty
    )
    final_conf = float(min(max(raw_score, Decimal("0")), Decimal("1")))

    return ScoredCandidateResult(
        candidate_info=candidate_info,
        confidence=final_conf,
        similarity=sim,
        id_cross=id_cross,
        hard_blocked=hard_blocked,
        block_reason=block_reason,
        soft_conflicts=tuple(soft_conflicts),
    )


def select_best_candidate(
    candidates: Iterable[Any],
    extract_candidate_info: Callable[[Any], Optional[Dict[str, Any]]],
    *,
    platform_name: str,
    platform_key: str = "",
    anime: Any = None,
    query: Optional[str] = None,
    max_attempts: int = 8,
    log_failure: bool = True,
    require_fuzzy_relevance: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    高召回候选择优器：
    - 过滤不在 ALLOWED_YEARS 的条目与窄黑名单硬冲突条目
    - 默认不因字面相似度偏低而拒收（兼容日文搜出纯罗马音/别名命中/新副标题场景）
    - 仅当 require_fuzzy_relevance=True（如 MAL 官方 API /v2/anime?q= 宽泛搜索）时校验最低相关性
    - 在所有合规候选中按（无软冲突/高置信度/命中目标年/命中idMal/原始顺位靠前）择优返回
    """
    allowed_years = get_allowed_years()
    desired_year = get_desired_year()
    desired_q = get_desired_quarter_index()
    viable: List[ScoredCandidateResult] = []
    attempts = 0

    for candidate in candidates:
        attempts += 1
        if attempts > max_attempts:
            break

        try:
            candidate_info = extract_candidate_info(candidate)
            if not candidate_info:
                continue

            candidate_name = candidate_info.get("name") or "未知名称"
            candidate_year = str(candidate_info.get("year") or "")
            candidate_id = candidate_info.get("id")

            if allowed_years and (not candidate_year or candidate_year not in allowed_years):
                logging.info(
                    f"跳过{platform_name}候选条目名称为 {candidate_name}，"
                    f"{platform_name}候选条目的放送年份 {candidate_year or '未知'} 不符合要求"
                )
                continue

            if anime is None and not query:
                scored = ScoredCandidateResult(
                    candidate_info=candidate_info,
                    confidence=1.0 if (not desired_year or candidate_year == desired_year) else 0.85,
                    similarity=1.0,
                    index=attempts,
                )
                viable.append(scored)
                if not desired_year or candidate_year == desired_year:
                    break
                continue

            scored = score_candidate_info(
                candidate_info,
                anime=anime,
                query=query,
                platform_key=platform_key or platform_name.lower(),
            )
            scored.index = attempts

            if scored.hard_blocked:
                logging.info(
                    f"跳过{platform_name}候选条目 {candidate_name} ({candidate_id})："
                    f"存在明确冲突 [{scored.block_reason}]"
                )
                continue

            if (
                require_fuzzy_relevance
                and not scored.id_cross
                and scored.similarity < FUZZY_CHANNEL_MIN_SIMILARITY
            ):
                logging.info(
                    f"跳过{platform_name}候选条目 {candidate_name} ({candidate_id})："
                    f"宽泛搜索通道标题相关性不足 (sim={scored.similarity:.2f})"
                )
                continue

            # 同文字体系（查询和候选均包含日文假名/汉字）时排除完全无关的单词撞车（如 sim=0.16）；
            # 若候选仅有英文/罗马音而查询为日文，则不设相似度下限以保留全部跨文字命中
            refs_check = collect_reference_titles(anime, extra_query=query)
            cand_titles_check = candidate_info.get("titles") or [candidate_name]
            both_cjk_kana = any(
                _CJK_RE.search(t) or _KANA_RE.search(t) for t in refs_check if t
            ) and any(
                _CJK_RE.search(str(t)) or _KANA_RE.search(str(t)) for t in cand_titles_check if t
            )
            if (
                both_cjk_kana
                and not scored.id_cross
                and scored.similarity < SAME_SCRIPT_FLOOR_SIMILARITY
            ):
                logging.info(
                    f"跳过{platform_name}候选条目 {candidate_name} ({candidate_id})："
                    f"同语种标题无实质重合 (sim={scored.similarity:.2f})"
                )
                continue

            viable.append(scored)

            # 提前短路：已无冲突、近乎满分、命中目标年（且若有目标季度也命中），无需继续拉取后续候选
            cand_q = parse_quarter_index(
                candidate_info.get("release_date") or candidate_info.get("date")
            )
            quarter_exact_ok = desired_q is None or cand_q == desired_q
            if (
                not scored.soft_conflicts
                and scored.confidence >= EARLY_STOP_CONFIDENCE
                and (not desired_year or candidate_year == desired_year)
                and quarter_exact_ok
            ):
                break

        except Exception as e:
            logging.warning(f"{platform_name}候选条目 {attempts} 处理失败: {e}")
            continue

    if not viable:
        if log_failure:
            logging.error(
                f"尝试{min(attempts, max_attempts)}次后，没有找到符合要求的 {platform_name} 候选条目"
            )
        return None

    # 排序优先级：
    # 1. 命中 idMal 交叉验证且无冲突
    # 2. 置信度分（融合了结构化相似度 + 季度/年份加分 - 软冲突微调，保留 2 位小数分档）
    # 3. 命中目标年份（如 2026 优先于 2025）
    # 4. 无软冲突
    # 5. 搜索引擎原始排名靠前（负 index）
    viable.sort(
        key=lambda item: (
            item.id_cross and not item.soft_conflicts,
            round(item.confidence, 2),
            bool(desired_year and str(item.candidate_info.get("year") or "") == desired_year),
            not item.soft_conflicts,
            -item.index,
        ),
        reverse=True,
    )
    best = viable[0]
    chosen = best.candidate_info
    logging.info(
        f"选中{platform_name}候选条目名称为 {chosen.get('name', '未知名称')}，"
        f"选中{platform_name}候选条目 {chosen.get('id')}，"
        f"放送年份: {chosen.get('year')} (得分: {best.confidence:.3f})"
    )
    return chosen
