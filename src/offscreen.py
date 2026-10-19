"""OFFSCREEN 탐지: 금칙어가 들어 있는데 사람 눈에는 안 보이게 숨긴 텍스트. (모집요강 정의 그대로)
 - font-size 0~1px
 - display:none (자기 자신 또는 조상) → 자식은 display 값이 inline 으로 나오므로 rect 가 0x0 인지로 판단
 - position 좌표 밀어내기 (left/top 큰 음수, 그 결과 rect 가 화면 왼쪽/위쪽 밖)
text-indent / transform / clip / 1px 상자 / visibility:hidden 은 기본 4종이 아니므로 extra.py(ETC)에서 다룬다.
투명(opacity 0, 글자색=배경색)은 TRANSPARENT 의 몫이므로 여기서 다루지 않는다.
금칙어 사전 게이트 때문에 정상적인 접근성용 오프스크린(a.skip-nav 등)은 걸리지 않는다."""
import re
from typing import Dict, List, Optional

from homoglyph import find_keywords

FAR = 1000          # 이 이상 멀리(px) 밀어내면 화면 밖으로 본다
_NUM = r"-?\d+(?:\.\d+)?"


def _px(v) -> Optional[float]:
    if v is None:
        return None
    m = re.match(rf"^\s*({_NUM})px\s*$", str(v))
    return float(m.group(1)) if m else None


def _translate(transform) -> tuple:
    """computed transform 은 'matrix(a,b,c,d,tx,ty)' 로 나온다. (tx, ty) 반환."""
    if not transform or transform == "none":
        return (0.0, 0.0)
    m = re.match(rf"^matrix\(\s*{_NUM}\s*,\s*{_NUM}\s*,\s*{_NUM}\s*,\s*{_NUM}\s*,\s*({_NUM})\s*,\s*({_NUM})\s*\)$", transform.strip())
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return (0.0, 0.0)


def _own_shift(st: Dict) -> bool:
    """text-indent / transform 으로 밀어낸 경우 (모집요강 OFFSCREEN 정의에 없는 방식)"""
    ti = _px(st.get("textIndent"))
    tx, ty = _translate(st.get("transform"))
    return (ti is not None and ti <= -FAR) or tx <= -FAR or ty <= -FAR


def offscreen_reasons(style: Dict, rect: Optional[Dict]) -> List[str]:
    """모집요강 OFFSCREEN 정의(font-size 0~1px / position 좌표 밀어내기 / display:none)에 해당하는 이유만 돌려준다.
    이 목록이 비어 있지 않으면 result.json 의 OFFSCREEN 이다."""
    reasons = []
    st = style or {}
    rc = rect or {}

    fs = _px(st.get("fontSize"))
    if fs is not None and fs <= 1:
        reasons.append(f"font-size:{st.get('fontSize')}")

    if st.get("display") == "none":
        reasons.append("display:none")
    elif rc and rc.get("width") == 0 and rc.get("height") == 0:
        reasons.append("display:none(ancestor)")           # 조상이 display:none → 자식 rect 는 0x0

    pos = st.get("position")
    if pos in ("absolute", "fixed", "relative"):
        for side in ("left", "top"):
            v = _px(st.get(side))
            if v is not None and v <= -FAR:
                reasons.append(f"{side}:{v:g}px")

    # 실제 위치 기준 (부모가 밀어냈어도 자식 rect 로 잡힌다). 스크롤 0 가정.
    # 자기 자신의 text-indent/transform 때문에 밀린 경우는 아래 extra 쪽 몫이다.
    if rc and rc.get("width", 0) > 0 and rc.get("height", 0) > 0 and not _own_shift(st):
        if rc.get("right", 1) <= 0:
            reasons.append("rect:화면 왼쪽 밖")
        if rc.get("bottom", 1) <= 0:
            reasons.append("rect:화면 위쪽 밖")

    return reasons


def _clips(st: Dict) -> bool:
    return (st.get("overflow") or "") in ("hidden", "clip") or (st.get("overflow") or "").startswith("hidden")


def extra_hide_reasons(style: Dict, rect: Optional[Dict]) -> List[str]:
    """기본 4종 정의에는 없지만 텍스트를 숨기는 방식. result_extra.json(ETC)용.
    (주최 측 답변: visibility:hidden, clip:rect(0,0,0,0), 1px 크기 상자+overflow:hidden 등은 기본 4종 정답이 아님)"""
    reasons = []
    st = style or {}
    rc = rect or {}

    if st.get("visibility") == "hidden":
        reasons.append("visibility:hidden")

    fs = _px(st.get("fontSize"))
    if rc and (fs is None or fs > 1) and _clips(st) and st.get("display") != "none" \
            and not (rc.get("width") == 0 and rc.get("height") == 0) \
            and (rc.get("width", 1) <= 1 or rc.get("height", 1) <= 1):
        reasons.append(f"1px 이하 크기 상자+overflow:hidden({rc.get('width')}x{rc.get('height')})")

    ti = _px(st.get("textIndent"))
    if ti is not None and ti <= -FAR:
        reasons.append(f"text-indent:{ti:g}px")

    tx, ty = _translate(st.get("transform"))
    if tx <= -FAR or ty <= -FAR:
        reasons.append(f"transform:{tx:g},{ty:g}")

    clip = (st.get("clip") or "").replace(" ", "")
    if clip in ("rect(0px,0px,0px,0px)", "rect(0,0,0,0)"):
        reasons.append("clip:rect(0,0,0,0)")
    cp = (st.get("clipPath") or "").replace(" ", "")
    if cp.startswith("inset(50%") or cp.startswith("inset(100%") or cp.startswith("circle(0"):
        reasons.append(f"clip-path:{cp}")

    return reasons


def detect_offscreen(text, style, rect=None):
    if not text or not text.strip():
        return None
    kws = find_keywords(text)
    if not kws:
        return None
    reasons = offscreen_reasons(style, rect)
    if not reasons:
        return None
    return {"evidence_text": text, "matched_keywords": kws, "reasons": reasons}


def detect_offscreen_in_elements(elements: List[Dict]) -> List[Dict]:
    findings, seen = [], set()
    for e in elements:
        text = e["direct_text"]; style = e["style"]; rect = e["rect"]     # 없으면 KeyError
        key = (e["url"], e["location"])
        if key in seen:
            continue
        d = detect_offscreen(text, style, rect)
        if d:
            seen.add(key)
            findings.append({"url": e["url"], "location": e["location"], "evidence_text": d["evidence_text"],
                             "technique": "OFFSCREEN", "is_violation": True,
                             "detail": {"keywords": d["matched_keywords"],
                                        "reason": "화면 밖/숨김 처리됨(" + ", ".join(d["reasons"]) + "), 금칙어: "
                                                  + ", ".join(d["matched_keywords"])}})
    return findings
