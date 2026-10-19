import re
from typing import Dict, List, Optional, Set, Tuple
from homoglyph import find_keywords

_COLOR = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)", re.I)
CONTRAST_LIMIT = 1.1

def _parse_color(c) -> Optional[Tuple[float, float, float, float]]:
    if not c:
        return None
    c = c.strip().lower()
    if c == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    m = _COLOR.match(c)
    if not m:
        return None
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)), a)

def _lum(r, g, b):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

def contrast_ratio(c1, c2) -> float:
    l1, l2 = _lum(*c1[:3]), _lum(*c2[:3])
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)

def detect_transparent(text, style, eff_opacity=None, eff_bg=None):
    if not text or not text.strip():
        return None
    kws = find_keywords(text)
    if not kws:
        return None
    reasons = []
    try:
        own = float(style.get("opacity", "1"))
    except Exception:
        own = 1.0
    op = own if eff_opacity is None else min(own, float(eff_opacity))
    if op <= 0.01:
        reasons.append(f"opacity={op}")
    fg = _parse_color(style.get("color"))
    if fg is not None:
        if fg[3] <= 0.01:
            reasons.append("color:transparent")
        else:
            bg = _parse_color(eff_bg if eff_bg is not None else style.get("backgroundColor"))
            if bg is not None and bg[3] > 0.5:
                ratio = contrast_ratio(fg, bg)
                if ratio < CONTRAST_LIMIT:
                    reasons.append(f"contrast={ratio:.2f}")
    # visibility:hidden 은 주최 측 답변상 기본 4종 정답이 아니다 → extra.py(ETC)에서 다룬다
    if not reasons:
        return None
    return {"evidence_text": text, "matched_keywords": kws, "reasons": reasons}

def detect_transparent_in_elements(elements):
    findings, seen = [], set()
    for e in elements:
        text = e["direct_text"]; e["eff_opacity"]; e["eff_bg"]      # 없으면 KeyError
        key = (e["url"], e["location"])
        if key in seen:
            continue
        d = detect_transparent(text, e["style"], e["eff_opacity"], e["eff_bg"])
        if d:
            seen.add(key)
            findings.append({"url": e["url"], "location": e["location"], "evidence_text": d["evidence_text"],
                             "technique": "TRANSPARENT", "is_violation": True,
                             "detail": {"keywords": d["matched_keywords"],
                                        "reason": "글자가 보이지 않게 처리됨(" + ", ".join(d["reasons"]) + "), 금칙어: "
                                                  + ", ".join(d["matched_keywords"])}})
    return findings
