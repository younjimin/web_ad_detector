import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Optional, Set

# 키릴/그리스 등 닮은꼴 -> 라틴 문자 치환표
# 주의: 대문자 키릴(В, Н, К, М, Т)은 소문자로 바꾸면 라틴 b/h/k/m/t 와 모양이 달라지므로
#       대문자 항목을 지우면 안 된다. (normalize 에서 치환 -> lower -> 치환 2회 적용)
# 이 표는 손으로 만든 것이므로, 항목을 늘릴 때는 Unicode confusables.txt(UTS #39)와 대조할 것.
CONFUSABLE_MAP: Dict[str, str] = {
    # 키릴 소문자
    "\u0430": "a",  # а
    "\u0435": "e",  # е
    "\u043e": "o",  # о
    "\u0440": "p",  # р
    "\u0441": "c",  # с
    "\u0443": "y",  # у
    "\u0445": "x",  # х
    "\u0455": "s",  # ѕ (dze)
    "\u0456": "i",  # і
    "\u0457": "i",  # ї (악센트 있는 i, 근사 치환)
    "\u0458": "j",  # ј
    # 키릴 대문자 (소문자화하면 모양이 달라지는 것들 포함)
    "\u0410": "a",  # А
    "\u0412": "b",  # В
    "\u0415": "e",  # Е
    "\u041a": "k",  # К
    "\u041c": "m",  # М
    "\u041d": "h",  # Н
    "\u041e": "o",  # О
    "\u0420": "p",  # Р
    "\u0421": "c",  # С
    "\u0422": "t",  # Т
    "\u0425": "x",  # Х
    # 그리스
    "\u03bf": "o",  # ο (omicron)
    "\u03bd": "v",  # ν (nu)
    "\u03c5": "u",  # υ (upsilon) - 모양이 u 와 비슷
}

# 금칙어 사전 (영문은 소문자로 정의)
BANNED_KEYWORDS: List[str] = [
    "카지노", "casino", "토토", "바카라", "슬롯", "홀덤", "먹튀", "첫충", "도박", "bet", "slot",
]


def _is_hangul_jamo(ch: str) -> bool:
    """한글 자모 블록 여부. 이 글자들은 JAMO(자모 분해) 탐지기의 몫이므로
    HOMOGLYPH 정규화에서는 건드리지 않는다.
    (NFKC 는 호환 자모 'ㅋㅏㅈㅣㄴㅗ' 를 음절 '카지노' 로 조합해버려서, 자모 분해를 닮은꼴 위장으로 오판하게 만든다)"""
    return (
        "\u1100" <= ch <= "\u11ff"      # 조합용 자모 (NFD 로 풀린 한글 포함)
        or "\u3130" <= ch <= "\u318f"   # 호환 자모 (ㅋ, ㅏ ...)
        or "\ua960" <= ch <= "\ua97f"   # 자모 확장-A
        or "\ud7b0" <= ch <= "\ud7ff"   # 자모 확장-B
    )


def _nfkc_except_jamo(text: str) -> str:
    """자모가 아닌 구간에만 NFKC 를 적용하고, 자모는 그대로 둔다."""
    out: List[str] = []
    buf: List[str] = []
    for ch in text:
        if _is_hangul_jamo(ch):
            if buf:
                out.append(unicodedata.normalize("NFKC", "".join(buf)))
                buf = []
            out.append(ch)
        else:
            buf.append(ch)
    if buf:
        out.append(unicodedata.normalize("NFKC", "".join(buf)))
    return "".join(out)


def _apply_confusable_map(text: str) -> str:
    return "".join(CONFUSABLE_MAP.get(ch, ch) for ch in text)


def normalize_for_matching(text: str) -> str:
    """
    1. NFKC: 전각 -> 반각 (ｍｅｇａ -> mega). 단, 한글 자모는 제외 (음절로 조합되는 것을 막기 위해)
    2. 닮은꼴 치환 (대문자 키릴 -> 라틴 소문자)
    3. 소문자화
    4. 닮은꼴 치환 한 번 더 (대문자 키릴 중 표에 없던 글자가 소문자가 되면서 표에 있는 글자로 바뀐 경우)
    """
    if not text:
        return ""
    t = _nfkc_except_jamo(text)
    t = _apply_confusable_map(t)
    t = t.lower()
    t = _apply_confusable_map(t)
    return t


# 숫자/기호 닮은꼴(leet): 라틴 문자 -> 그 글자 대신 쓰일 수 있는 숫자·기호
LEET_SUBS: Dict[str, str] = {
    "a": "4@", "b": "8", "e": "3", "g": "9", "i": "1!",
    "l": "1", "o": "0", "s": "5$", "t": "7",
}


@lru_cache(maxsize=None)
def _leet_pattern(keyword: str):
    """금칙어의 각 글자를 [글자 + 닮은 숫자/기호] 문자 클래스로 바꾼 정규식.
    예) casino -> [c][a4@][s5$][i1!][n][o0]  (앞뒤는 영문/숫자 경계)"""
    parts = ["[" + re.escape(ch + LEET_SUBS.get(ch, "")) + "]" for ch in keyword]
    return re.compile(r"(?<![a-z0-9])" + "".join(parts) + r"(?![a-z0-9])")


def find_leet_keywords(text: str) -> List[str]:
    """숫자/기호로 위장된 영문 금칙어 탐지. text 는 normalize_for_matching 을 거친 것.
    오탐 방지: 매치 안에 '치환 문자가 1개 이상' 있고, '영문자 수 >= 치환 문자 수' 일 때만 인정.
      c4s1n0 (영문 3, 치환 3) -> 인정   /  837 (영문 0, 치환 3) -> 기각   /  B37 (영문 1, 치환 2) -> 기각
    이 임계값은 휴리스틱이므로 실제 데이터를 보며 조정할 것."""
    found = []
    for kw in BANNED_KEYWORDS:
        if not re.match(r"^[a-z0-9]+$", kw):
            continue
        for m in _leet_pattern(kw).finditer(text):
            matched = m.group()
            letters = sum(c.isalpha() for c in matched)
            subs = len(matched) - letters
            if subs >= 1 and letters >= subs:
                found.append(kw)
                break
    return found


def find_keywords(text: str) -> List[str]:
    """
    text 안에서 발견되는 금칙어 목록.
    영문 금칙어는 (?<![a-z0-9])...(?![a-z0-9]) 로 경계를 잡는다 (\\b 는 한글을 단어 문자로 취급).
    """
    if not text:
        return []

    found = []
    text_lower = text.lower()

    for kw in BANNED_KEYWORDS:
        if re.match(r"^[a-z0-9]+$", kw):
            pattern = rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])"
            if re.search(pattern, text_lower):
                found.append(kw)
        else:
            if kw in text_lower:
                found.append(kw)

    return found


def detect_homoglyph(raw_text: str) -> Optional[Dict]:
    """
    원문에서는 안 걸리고 정규화본에서만 걸리는 금칙어, 또는 숫자/기호로 위장된 금칙어가 있으면
    HOMOGLYPH 위장으로 판정.
    """
    if not raw_text or not raw_text.strip():
        return None

    raw_found = set(find_keywords(raw_text))

    norm_text = normalize_for_matching(raw_text)
    norm_found = set(find_keywords(norm_text))

    # (a) 정규화로 새로 드러난 금칙어  (b) 숫자/기호로 위장된 금칙어
    newly_revealed = sorted((norm_found - raw_found) | set(find_leet_keywords(norm_text)))

    if newly_revealed:
        return {
            "evidence_text": raw_text,  # 정규화 전 원문 그대로
            "normalized_text": norm_text,
            "matched_keywords": newly_revealed,
        }
    return None


def detect_homoglyph_in_elements(elements: List[Dict]) -> List[Dict]:
    """
    크롤러 elements 의 direct_text 만 검사한다. (url, location) 단위로 1건.
    direct_text 필드가 없으면 크롤러 수정이 빠진 것이므로 조용히 넘어가지 않고 에러를 낸다.
    """
    findings: List[Dict] = []
    seen_locations: Set[tuple] = set()

    for elem in elements:
        if "direct_text" not in elem:
            raise KeyError(
                "elements 에 'direct_text' 필드가 없습니다. "
                "크롤러 JS 의 results.push 안에 direct_text: trimmedDirectText 를 추가하세요."
            )

        url = elem.get("url", "")
        location = elem.get("location", "")
        loc_key = (url, location)
        if loc_key in seen_locations:
            continue

        target_text = elem["direct_text"]
        if not target_text or not target_text.strip():
            continue

        detection = detect_homoglyph(target_text)
        if detection:
            seen_locations.add(loc_key)
            findings.append({
                "url": url,
                "location": location,
                "evidence_text": detection["evidence_text"],
                "technique": "HOMOGLYPH",
                "is_violation": True,
            })

    return findings