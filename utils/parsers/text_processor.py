# utils/parsers/text_processor.py
# 存放搜索词清洗与文本预处理工具函数

from html import unescape
import re
from typing import List

# Bangumi 搜索接口会把空白后的前导 "-" 解析为布尔 NOT 排除词（如 "-Finale-" / "-Second Season-" 会排除词项）
# 同时兼容紧贴在日文/汉字后的成对连字符副标题（如 "戦車椅子-TANK CHAIR-"）
_PAIRED_HYPHEN_SUBTITLE_RE = re.compile(
    r"(?:(?<=[\s\u3000!！?？\u3040-\u30ff\u3400-\u9fff])|^)-+([^-]+?)-+(?=[\s\u3000!！?？]|$)"
)
_BOOL_EXCLUDE_HYPHEN_RE = re.compile(r"(?:^|[\s\u3000]+)-+")
# 仅替换独立噪音符号；保留词内连字符（如 S-Rank / U-17）及小数点/缩写点（如 2.5次元 / Dr.STONE / 1/2）
_NOISY_SYMBOL_RE = re.compile(r"[*@#\+]|(?<![A-Za-z0-9])\.|\.(?![A-Za-z0-9])", flags=re.UNICODE)

# 冗余第1クール括号后缀（如 "薬屋のひとりごと 第3期（第1クール）"），用于初搜 0 结果时的精简重搜
_REDUNDANT_COUR1_SUFFIX_RE = re.compile(
    r"\s*[\(（\[]\s*(?:第\s*)?[1一]\s*(?:st\s*)?(?:クール|cour|part)\s*[\)）\]]\s*$",
    re.IGNORECASE,
)
# 波浪号或空格分隔的超长副标题，用于初搜 0 结果时提取主标题兜底重搜
_LONG_SUBTITLE_SPLIT_RE = re.compile(
    r"^(.{4,25}?)(?:\s+[〜～\-].{6,}|[〜～].{6,}[〜～]?|\s+.{14,})$"
)


def sanitize_bangumi_keyword(keyword: str) -> str:
    """
    清洗可能触发 Bangumi 搜索布尔排除语法的前导连字符与成对连字符副标题，保留词内连字符。
    """
    if not keyword:
        return ""
    cleaned = _PAIRED_HYPHEN_SUBTITLE_RE.sub(r" \1 ", str(keyword))
    cleaned = _BOOL_EXCLUDE_HYPHEN_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def preprocess_name(original_name: str) -> str:
    """
    预处理原始名称：解码 HTML 实体，安全清理噪音符号与布尔排除连字符，
    同时保留词内连字符（如 S-Rank / U-17）与数字/缩写点号（如 2.5 / Dr.STONE）。
    """
    if original_name is None:
        return ""
    text = unescape(str(original_name))
    text = sanitize_bangumi_keyword(text)
    text = _NOISY_SYMBOL_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_query_variants(raw_or_processed: str) -> List[str]:
    """
    构建主搜索词及仅在 0 结果时使用的精简变体（去重，保持顺序）：
    1. 标准 preprocess_name 结果
    2. 剥离末尾冗余 "（第1クール）" 括号（如 "薬屋のひとりごと 第3期（第1クール）" -> "薬屋のひとりごと 第3期"）
    3. 去除方括号/星号装饰（如 "Battle Spirits [Re] 絶界の空" / "ケロロ軍曹☆"）
    4. 超长轻改副标题提取主标题（仅在不含季数丢失风险时生成）
    """
    primary = preprocess_name(raw_or_processed)
    if not primary:
        return []

    variants: List[str] = [primary]
    seen = {primary.lower()}

    def _add(candidate: str) -> None:
        c = re.sub(r"\s+", " ", candidate).strip()
        if len(c) >= 2 and c.lower() not in seen:
            seen.add(c.lower())
            variants.append(c)

    no_cour1 = _REDUNDANT_COUR1_SUFFIX_RE.sub("", primary).strip()
    if no_cour1 != primary:
        _add(no_cour1)

    no_decor = re.sub(r"[\[\]【】☆★♪♡♥]", " ", no_cour1)
    _add(no_decor)

    # 常见中日异体字转换兜底（如 "冰剣" <-> "氷剣"，解决 AniList 仅收录标准日文汉字 "氷剣" 的情况）
    kanji_variant = no_cour1.translate(str.maketrans({"冰": "氷", "剑": "剣"}))
    if kanji_variant != no_cour1:
        _add(kanji_variant)

    # 罗马数字 ASCII <-> Unicode 互转兜底（如 "ダイヤのA actII" <-> "ダイヤのA actⅡ"，AniList 搜索不自动做 NFKC 归一）
    if "Ⅲ" in no_cour1 or "Ⅱ" in no_cour1:
        _add(no_cour1.replace("Ⅲ", "III").replace("Ⅱ", "II"))
    else:
        roman_to_unicode = re.sub(
            r"(?:(?<=[\s:：\-〜～A-Za-z\u3040-\u30ff\u3400-\u9fff])|^)(III|II)(?=$|[\s:：\-〜～!！?？])",
            lambda m: "Ⅲ" if m.group(1).upper() == "III" else "Ⅱ",
            no_cour1,
        )
        if roman_to_unicode != no_cour1:
            _add(roman_to_unicode)

    m_sub = _LONG_SUBTITLE_SPLIT_RE.match(no_cour1)
    if m_sub:
        head = m_sub.group(1).strip()
        tail = no_cour1[len(head) :]
        # 若尾部包含明确季数/クール标识，不剥离尾部以免丢失季数语义
        if not re.search(
            r"(?:第\s*[2-9二三四五]|season\s*[2-9]|[2-9](?:nd|rd|th)|[2-9]\s*クール|part\s*[2-9]|II|III|２|３)",
            tail,
            re.IGNORECASE,
        ):
            _add(head)

    return variants
