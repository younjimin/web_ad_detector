import unicodedata
from typing import Dict, List, Optional, Set

from homoglyph import find_keywords  # 금칙어 매칭은 HOMOGLYPH와 동일한 함수/사전 활용

CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"                  
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"                 
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"        

# 빠른 인덱스 검색을 위한 딕셔너리
CHO_MAP = {c: i for i, c in enumerate(CHOSEONG)}
JUNG_MAP = {c: i for i, c in enumerate(JUNGSEONG)}
JONG_MAP = {c: i for i, c in enumerate(JONGSEONG)}

# ㄸ, ㅃ, ㅉ 는 받침이 될 수 없음
NO_JONGSEONG_SET = {"ㄸ", "ㅃ", "ㅉ"}


def compose_jamo(text: str) -> str:
    """
    text 안의 '자모 연속 구간'을 음절로 직접 재조합한 사본을 반환함
    """
    if not text:
        return ""

    # 1. 조합용 자모 먼저 NFC 정규화
    text = unicodedata.normalize("NFC", text)

    result = []
    i = 0
    n = len(text)

    while i < n:
        c1 = text[i]

        # 초성 후보 확인
        if c1 in CHO_MAP and (i + 1 < n) and (text[i + 1] in JUNG_MAP):
            cho_idx = CHO_MAP[c1]
            jung_idx = JUNG_MAP[text[i + 1]]
            jong_idx = 0  # 기본: 받침 없음
            consumed = 2

            # 종성 가능성 검사
            if i + 2 < n:
                c3 = text[i + 2]
                # c3가 실제 종성 자음이어야 함 (공백 " " 및 받침 불가 자음 제외)
                if c3 in JONG_MAP and c3 != " " and c3 not in NO_JONGSEONG_SET:
                    # c3 뒤(i+3)에 바로 모음이 연결되면 c3는 다음 음절 초성이 됨
                    if not ((i + 3 < n) and (text[i + 3] in JUNG_MAP)):
                        jong_idx = JONG_MAP[c3]
                        consumed = 3

            # 유니코드 음절 코드 계산 및 합성
            syllable_code = 0xAC00 + (cho_idx * 21 + jung_idx) * 28 + jong_idx
            result.append(chr(syllable_code))
            i += consumed
        else:
            result.append(c1)
            i += 1

    return "".join(result)


def detect_jamo(raw_text: str) -> Optional[Dict]:
    """
    재조합본에서만 새로 드러난 금칙어가 있으면 dict 반환, 아니면 None.
    """
    if not raw_text or not raw_text.strip():
        return None

    raw_found = set(find_keywords(raw_text))
    recomposed_text = compose_jamo(raw_text)
    recomposed_found = set(find_keywords(recomposed_text))

    # 재조합본에서만 새로 발견된 금칙어 집합 연산
    newly_revealed = list(recomposed_found - raw_found)

    if newly_revealed:
        return {
            "evidence_text": raw_text,  # 원문 유지
            "recomposed_text": recomposed_text,
            "matched_keywords": sorted(newly_revealed)
        }

    return None


def detect_jamo_in_elements(elements: List[Dict]) -> List[Dict]:
    """
    크롤러가 수집한 elements에서 JAMO 위장을 탐지.
    """
    findings: List[Dict] = []
    
    # 1단계 direct_text 검출 결과 및 위치 기록
    direct_detected_locations: Set[tuple] = set()

    for elem in elements:
        url = elem["url"]
        location = elem["location"]
        loc_key = (url, location)

        # 동일한 (url, location) 중복 방지
        if loc_key in direct_detected_locations:
            continue

        target_text = elem["direct_text"]

        if not target_text or not target_text.strip():
            continue

        detection = detect_jamo(target_text)
        if detection:
            direct_detected_locations.add(loc_key)
            findings.append({
                "url": url,
                "location": location,
                "evidence_text": detection["evidence_text"],
                "technique": "JAMO",
                "is_violation": True,
                "_is_direct": True
            })

    # 2단계 full_text (쪼개진 자모 span 복합) 검사
    full_candidates: List[Dict] = []

    for elem in elements:
        url = elem["url"]
        location = elem["location"]
        loc_key = (url, location)

        if loc_key in direct_detected_locations:
            continue

        full_text = elem["full_text"]
        if not full_text or not full_text.strip():
            continue

        detection = detect_jamo(full_text)
        if detection:
            full_candidates.append({
                "url": url,
                "location": location,
                "evidence_text": detection["evidence_text"],
                "technique": "JAMO",
                "is_violation": True,
                "_is_direct": False
            })

    # 2단계 후보 중 가장 안쪽(가장 깊은/선택자 경로가 긴) 요소만 선별
    filtered_full: List[Dict] = []
    for cand in full_candidates:
        cand_url = cand["url"]
        cand_loc = cand["location"]

        is_ancestor = False
        for other in full_candidates:
            if other["url"] == cand_url and other["location"] != cand_loc:
                if other["location"].startswith(cand_loc + " > "):
                    is_ancestor = True
                    break

        if not is_ancestor:
            filtered_full.append(cand)

    # 결과 취합 및 내부 필드 정돈
    all_results = []
    for item in findings + filtered_full:
        res = dict(item)
        res.pop("_is_direct", None)
        all_results.append(res)

    return all_results