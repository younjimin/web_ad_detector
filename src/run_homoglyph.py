import json
from homoglyph import detect_homoglyph_in_elements

with open("elements_dump.json", encoding="utf-8") as f:
    data = json.load(f)

findings = detect_homoglyph_in_elements(data["elements"])

print(f"HOMOGLYPH 검출: {len(findings)}건")
for fd in findings:
    print(fd["url"])
    print("  location:", fd["location"])
    print("  evidence:", fd["evidence_text"])

with open("findings_homoglyph.json", "w", encoding="utf-8") as f:
    json.dump(findings, f, ensure_ascii=False, indent=2)