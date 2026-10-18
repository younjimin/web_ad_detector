"""elements_dump.json(스크립트와 같은 폴더)을 읽어 구현된 탐지기를 모두 돌린다.
사용: python run_detectors.py"""
import json
from pathlib import Path

from homoglyph import detect_homoglyph_in_elements
from jamo import detect_jamo_in_elements
from transparent import detect_transparent_in_elements
from offscreen import detect_offscreen_in_elements

src = Path(__file__).with_name("elements_dump.json")
print("읽는 json:",  resolve())
with open(src, encoding="utf-8") as f:
    elements = json.load(f)["elements"]

findings = []
findings += detect_homoglyph_in_elements(elements)
findings += detect_jamo_in_elements(elements)
findings += detect_transparent_in_elements(elements)
findings += detect_offscreen_in_elements(elements)

for tech in ("HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN"):
    group = [x for x in findings if x["technique"] == tech]
    print(f"\n[{tech}] {len(group)}건")
    for x in group:
        print(" ", x["url"])
        print("    location:", x["location"])
        print("    evidence:", x["evidence_text"])

out = Path(__file__).with_name("findings.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(findings, f, ensure_ascii=False, indent=2)
print("\n저장:", out.resolve())