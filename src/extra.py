"""추가 탐지(ETC): 모집요강 기본 4종(HOMOGLYPH/JAMO/TRANSPARENT/OFFSCREEN) 정의에는 없지만
광고 문구를 숨기는 방식. 결과는 result.json 이 아니라 result_extra.json 에 technique="ETC" 로 담긴다.

 - visibility:hidden
 - clip:rect(0,0,0,0) / clip-path 로 잘라내기
 - 1px 이하 크기 상자 + overflow:hidden
 - text-indent / transform 으로 화면 밖으로 밀어내기
 - 제로폭 문자(ZWSP 등)를 글자 사이에 끼워 넣어 키워드 매칭을 피하기

주최 측 안내: 기본 4종에 해당하는 스타일이 함께 적용된 요소는 기본 유형으로만 적고,
기본 4종에 해당하지 않을 때만 추가 탐지로 적는다 → 같은 요소에 기본 4종 결과가 있으면 여기서는 내지 않는다."""
import re
from typing import Dict, List

from homoglyph import find_keywords
from offscreen import extra_hide_reasons

_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")


_HIDE_NAMES = (("visibility", "visibility:hidden 은닉"), ("1px", "1px 상자+overflow:hidden 은닉"),
               ("text-indent", "text-indent 화면 밖 은닉"), ("transform", "transform 화면 밖 은닉"),
               ("clip", "clip 잘라내기 은닉"))


def _hide_name(reason: str) -> str:
    for prefix, name in _HIDE_NAMES:
        if reason.startswith(prefix):
            return name
    return "텍스트 은닉"


def detect_extra(text, style, rect=None):
    """[(extra_finding 이름, 이유 문장)] 목록. 없으면 빈 리스트."""
    if not text or not text.strip():
        return []
    kws = find_keywords(text)
    if not kws:
        return []
    out = []
    hide = extra_hide_reasons(style, rect)
    if hide:
        out.append((_hide_name(hide[0]),
                    "기본 4종 밖의 숨김 방식(" + ", ".join(hide) + "), 금칙어: " + ", ".join(kws)))
    if _ZERO_WIDTH.search(text):
        out.append(("제로폭 문자 삽입",
                    "글자 사이에 보이지 않는 제로폭 문자를 끼워 키워드 필터를 피함, 금칙어: " + ", ".join(kws)))
    return out


def detect_extra_in_elements(elements: List[Dict], basic_findings: List[Dict]) -> List[Dict]:
    """basic_findings: 이미 기본 4종으로 잡힌 건 (같은 url+location 이면 건너뛴다)."""
    taken = {(f["url"], f["location"]) for f in basic_findings}
    findings, seen = [], set()
    for e in elements:
        key0 = (e["url"], e["location"])
        if key0 in taken:
            continue
        for name, why in detect_extra(e["direct_text"], e["style"], e["rect"]):
            key = (e["url"], e["location"], name)
            if key in seen:
                continue
            seen.add(key)
            findings.append({"url": e["url"], "location": e["location"], "evidence_text": e["direct_text"],
                             "technique": "ETC", "extra_finding": name, "is_violation": True,
                             "detail": {"reason": why}})
    return findings
