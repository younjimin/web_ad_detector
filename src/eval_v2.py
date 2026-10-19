"""정답지(expected.json)가 있는 테스트 사이트로 탐지 정확도를 잰다.

사용법
  1. 테스트 사이트 폴더에서 서버를 띄운다:   python -m http.server 8002
  2. 다른 터미널에서 src 폴더로 가서 실행:   python eval_v2.py ..\\test_site_v2 8002

expected.json 은 [페이지 파일명, 증거 문구, 기법] 목록이다. 기법이 "__NEG__" 인 항목은 잡히면 안 되는 문구다.
result.json 과 result_extra.json 의 결과를 합쳐서 정답과 비교하고, 재현율과 오탐을 출력한다.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_core  # noqa: E402


def page_name(finding):
    return finding["url"].split("/")[-1].split("?")[0]


def main():
    folder, port = sys.argv[1], sys.argv[2]
    with open(os.path.join(folder, "expected.json"), encoding="utf-8") as fh:
        expected = [e for e in json.load(fh) if e[2] != "__NEG__"]

    with tempfile.TemporaryDirectory() as out_dir:          # 결과 파일은 임시 폴더에 두고 버린다
        ret = scan_core.run_scan(f"http://localhost:{port}/index.html", out_dir=out_dir,
                                 log=lambda s: None, max_pages=50)
    basic, extra = ret["result"]["findings"], ret["extra"]["findings"]
    found = basic + extra

    matched, missed = set(), []
    for page, evidence, technique in expected:
        hits = [i for i, f in enumerate(found)
                if page_name(f) == page and evidence in f["evidence_text"] and f["technique"] == technique]
        if hits:
            matched.add(hits[0])
        else:
            actual = [f["technique"] for f in found if page_name(f) == page and evidence in f["evidence_text"]]
            missed.append((page, evidence, technique, actual))
    false_positives = [f for i, f in enumerate(found) if i not in matched]

    recall = len(matched) / len(expected)
    print(f"페이지 {ret['pages']}개, 탐지 {len(basic)}건 (+추가 {len(extra)}건)")
    print(f"정답 {len(expected)}건 중 {len(matched)}건 적중 (재현율 {recall:.0%}), 오탐 {len(false_positives)}건")
    for page, evidence, technique, actual in missed:
        print(f"  놓침: {page} / {evidence} / 정답 {technique} / 실제 {actual or '없음'}")
    for f in false_positives:
        print(f"  오탐: {f['technique']} / {page_name(f)} / {f['evidence_text'][:50]}")


if __name__ == "__main__":
    main()