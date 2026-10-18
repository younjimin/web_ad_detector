"""test_site_v2 로 정확도를 재는 스크립트.
사용:  (test_site_v2 폴더에서) python -m http.server 8002   ->  다른 터미널에서  python eval_v2.py test_site_v2 8002
expected.json 의 정답 목록과 탐지 결과를 비교해 재현율과 오탐을 출력한다."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_core  # noqa: E402

folder, port = sys.argv[1], sys.argv[2]
r = scan_core.run_scan(f"http://localhost:{port}/index.html", out_dir=os.path.join(folder, "out"),
                       log=lambda s: None, max_pages=50)
fs = r["result"]["findings"]
exp = json.load(open(os.path.join(folder, "expected.json"), encoding="utf-8"))
pos = [e for e in exp if e[2] != "__NEG__"]
page_of = lambda f: f["url"].split("/")[-1].split("?")[0]
tp, miss, used = 0, [], set()
for page, ev, tech in pos:
    hit = [i for i, f in enumerate(fs) if page_of(f) == page and ev in f["evidence_text"] and f["technique"] == tech]
    if hit:
        tp += 1
        used.add(hit[0])
    else:
        miss.append((page, ev, tech, [f["technique"] for f in fs if page_of(f) == page and ev in f["evidence_text"]]))
fp = [f for i, f in enumerate(fs) if i not in used]
print(f"pages={r['pages']} findings={len(fs)}  정답 {len(pos)}건 중 {tp}건 적중(재현율 {tp / len(pos):.0%}), 오탐 {len(fp)}건")
for m in miss:
    print("  놓침:", m)
for f in fp:
    print("  오탐:", f["technique"], page_of(f), f["evidence_text"][:50])