"""요소 목록 -> 탐지기 4종 -> 정리된 findings. (크롤러와 분리해 두어 json 덤프로도 테스트 가능)"""
from typing import Dict, List

from homoglyph import detect_homoglyph_in_elements
from src.extra import detect_extra_in_elements
from jamo import detect_jamo_in_elements
from offscreen import detect_offscreen_in_elements
from transparent import detect_transparent_in_elements

DETECTORS = [
    ("HOMOGLYPH", detect_homoglyph_in_elements),
    ("JAMO", detect_jamo_in_elements),
    ("TRANSPARENT", detect_transparent_in_elements),
    ("OFFSCREEN", detect_offscreen_in_elements),
]


def run_all_detectors(elements: List[Dict]) -> List[Dict]:
    """한 탐지기가 예외를 내도 나머지는 계속 돈다 (한 건 때문에 전체 결과를 잃지 않기 위해).
    (url, location, technique) 가 같은 건 한 건만 남긴다."""
    findings: List[Dict] = []
    seen = set()
    for name, fn in DETECTORS:
        try:
            found = fn(elements)
        except Exception as e:                      # 탐지기 버그가 전체를 죽이지 않게
            print(f"[!] {name} 탐지기 오류: {type(e).__name__}: {e}")
            continue
        for f in found:
            key = (f["url"], f["location"], f["technique"])
            if key in seen:
                continue
            seen.add(key)
            findings.append(f)
    return findings


def run_extra_detectors(elements: List[Dict], basic_findings: List[Dict]) -> List[Dict]:
    """기본 4종 밖의 추가 탐지(ETC). 예외가 나도 빈 목록을 돌려줘 기본 결과에 영향을 주지 않는다."""
    try:
        return detect_extra_in_elements(elements, basic_findings)
    except Exception as e:
        print(f"[!] 추가 탐지기 오류: {type(e).__name__}: {e}")
        return []
