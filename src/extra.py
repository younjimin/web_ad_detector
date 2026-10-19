"""추가 탐지(ETC): 모집요강의 기본 4종 정의에는 없지만 광고 문구를 숨기는 방식을 찾는다.
결과는 result.json 이 아니라 result_extra.json 에 technique="ETC" 로 들어간다.

  - visibility:hidden
  - clip:rect(0,0,0,0), clip-path 로 잘라내기
  - 1px 이하 크기 상자 + overflow:hidden
  - text-indent, transform 으로 화면 밖에 두기
  - 글자 사이에 제로폭 문자를 끼워 키워드 매칭 피하기

주최 측 안내에 따라, 기본 4종 결과가 이미 있는 요소는 여기서 다시 내지 않는다.
"""
import re
from typing import Dict, List

from homoglyph import find_keywords
from offscreen import extra_hide_reasons

# 소스에 눈에 보이지 않는 문자를 직접 넣지 않으려고 \u 이스케이프로 적는다
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

# extra_hide_reasons 가 돌려주는 이유 문장의 앞부분 -> result_extra.json 의 extra_finding 이름
_HIDE_NAMES = (
    ("visibility", "visibility:hidden 은닉"),
    ("1px", "1px 상자+overflow:hidden 은닉"),
    ("text-indent", "text-indent 화면 밖 은닉"),
    ("transform", "transform 화면 밖 은닉"),
    ("clip", "clip 잘라내기 은닉"),
)


def _hide_name(reason: str) -> str:
    for prefix, name in _HIDE_NAMES:
        if reason.startswith(prefix):
            return name
    return "텍스트 은닉"


def detect_extra(text, style, rect=None):
    """(extra_finding 이름, 판정 이유) 목록을 돌려준다. 해당 없으면 빈 목록."""
    if not text or not text.strip():
        return []
    keywords = find_keywords(text)
    if not keywords:
        return []

    found = []
    kw_text = ", ".join(keywords)
    hide = extra_hide_reasons(style, rect)
    if hide:
        found.append((_hide_name(hide[0]),
                      f"기본 4종 밖의 숨김 방식({', '.join(hide)}), 금칙어: {kw_text}"))
    if _ZERO_WIDTH.search(text):
        found.append(("제로폭 문자 삽입",
                      f"글자 사이에 보이지 않는 제로폭 문자를 끼워 키워드 필터를 피함, 금칙어: {kw_text}"))
    return found


def detect_extra_in_elements(elements: List[Dict], basic_findings: List[Dict]) -> List[Dict]:
    """basic_findings 에 같은 url·location 이 있는 요소는 건너뛴다."""
    already = {(f["url"], f["location"]) for f in basic_findings}
    findings, seen = [], set()
    for el in elements:
        if (el["url"], el["location"]) in already:
            continue
        for name, reason in detect_extra(el["direct_text"], el["style"], el["rect"]):
            key = (el["url"], el["location"], name)
            if key in seen:
                continue
            seen.add(key)
            findings.append({"url": el["url"], "location": el["location"], "evidence_text": el["direct_text"],
                             "technique": "ETC", "extra_finding": name, "is_violation": True,
                             "detail": {"reason": reason}})
    return findings
