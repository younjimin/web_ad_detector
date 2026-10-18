import unicodedata
from typing import Dict, List, Optional, Set

from homoglyph import find_keywords

CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSEONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

CHO_MAP = {c: i for i, c in enumerate(CHOSEONG)}
JUNG_MAP = {c: i for i, c in enumerate(JUNGSEONG)}
JONG_MAP = {c: i for i, c in enumerate(JONGSEONG) if i > 0}  # 0번(받침 없음=공백)은 제외

NO_JONGSEONG_SET = {"ㄸ", "ㅃ", "ㅉ"}


def compose_jamo(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    result = []
    i = 0
    n = len(text)
    while i < n:
        c1 = text[i]
        if c1 in CHO_MAP and (i + 1 < n) and (text[i + 1] in JUNG_MAP):
            cho_idx = CHO_MAP[c1]
            jung_idx = JUNG_MAP[text[i + 1]]
            jong_idx = 0
            consumed = 2
            if i + 2 < n:
                c3 = text[i + 2]
                if c3 in JONG_MAP and c3 not in NO_JONGSEONG_SET:
                    if (i + 3 < n) and (text[i + 3] in JUNG_MAP):
                        pass
                    else:
                        jong_idx = JONG_MAP[c3]
                        consumed = 3
            syllable_code = 0xAC00 + (cho_idx * 21 + jung_idx) * 28 + jong_idx
            result.append(chr(syllable_code))
            i += consumed
        else:
            result.append(c1)
            i += 1
    return "".join(result)


def detect_jamo(raw_text: str) -> Optional[Dict]:
    if not raw_text or not raw_text.strip():
        return None
    raw_found = set(find_keywords(raw_text))
    recomposed_text = compose_jamo(raw_text)
    recomposed_found = set(find_keywords(recomposed_text))
    newly_revealed = list(recomposed_found - raw_found)
    if newly_revealed:
        return {"evidence_text": raw_text, "recomposed_text": recomposed_text,
                "matched_keywords": sorted(newly_revealed)}
    return None


def detect_jamo_in_elements(elements: List[Dict]) -> List[Dict]:
    findings: List[Dict] = []
    direct_detected_locations: Set[tuple] = set()
    for elem in elements:
        url = elem["url"]
        location = elem["location"]
        if (url, location) in direct_detected_locations:
            continue
        target_text = elem["direct_text"]
        if not target_text or not target_text.strip():
            continue
        detection = detect_jamo(target_text)
        if detection:
            direct_detected_locations.add((url, location))
            findings.append({"url": url, "location": location,
                             "evidence_text": detection["evidence_text"],
                             "technique": "JAMO", "is_violation": True, "_is_direct": True})
    full_candidates: List[Dict] = []
    full_seen: Set[tuple] = set()
    for elem in elements:
        url = elem["url"]
        location = elem["location"]
        loc_key = (url, location)
        if loc_key in direct_detected_locations or loc_key in full_seen:
            continue
        full_text = elem["full_text"]
        if not full_text or not full_text.strip():
            continue
        detection = detect_jamo(full_text)
        if detection:
            full_seen.add(loc_key)
            full_candidates.append({"url": url, "location": location,
                                    "evidence_text": detection["evidence_text"],
                                    "technique": "JAMO", "is_violation": True, "_is_direct": False})
    flagged_all = [(f["url"], f["location"]) for f in findings] + [(c["url"], c["location"]) for c in full_candidates]
    filtered_full: List[Dict] = []
    for cand in full_candidates:
        cand_url = cand["url"]
        cand_loc = cand["location"]
        is_ancestor = any(u == cand_url and l.startswith(cand_loc + " > ") for (u, l) in flagged_all)
        if not is_ancestor:
            filtered_full.append(cand)
    all_results = []
    for item in findings + filtered_full:
        res = dict(item)
        res.pop("_is_direct", None)
        all_results.append(res)
    return all_results