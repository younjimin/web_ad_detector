import json, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from  pipeline import run_all_detectors
from  result_writer import build_result, validate_result, write_result

T0 = datetime(2026, 10, 18, 9, 0, 0).astimezone()
F = lambda u, l, t: {"url": u, "location": l, "evidence_text": "카지노", "technique": t, "is_violation": True, "_x": 1}

def test_meta_and_ids():
    r = build_result("http://a/", T0, T0 + timedelta(seconds=12.345), [F("u", "p", "JAMO"), F("u", "q", "OFFSCREEN")])
    assert r["meta"]["elapsed_sec"] == 12.35 and r["meta"]["entry_url"] == "http://a/"
    assert [x["id"] for x in r["findings"]] == ["f_001", "f_002"]
    assert list(r["meta"]) == ["topic", "entry_url", "started_at", "finished_at", "elapsed_sec", "tool_version"]
def test_only_spec_keys():
    r = build_result("u", T0, T0, [F("u", "p", "JAMO")])
    assert list(r["findings"][0]) == ["id", "url", "is_violation", "location", "evidence_text", "technique"]
def test_valid_passes():
    assert validate_result(build_result("u", T0, T0, [F("u", "p", "JAMO")])) == []
def test_bad_technique_and_duplicate():
    r = build_result("u", T0, T0, [F("u", "p", "JAMO"), F("u", "p", "JAMO"), F("u", "q", "NOPE")])
    e = validate_result(r)
    assert any("중복" in x for x in e) and any("technique" in x for x in e)
def test_same_location_two_techniques_allowed():
    assert validate_result(build_result("u", T0, T0, [F("u", "p", "JAMO"), F("u", "p", "OFFSCREEN")])) == []
def test_write_utf8_no_bom():
    r = build_result("u", T0, T0, [F("u", "p", "JAMO")])
    with tempfile.TemporaryDirectory() as d:
        p = write_result(r, Path(d) / "sub" / "result.json")
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and "카지노".encode() in raw
        assert json.loads(raw.decode("utf-8")) == r
def test_empty_findings_ok():
    assert validate_result(build_result("u", T0, T0, [])) == []
def test_pipeline_survives_detector_error():
    assert run_all_detectors([{"url": "u"}]) == []       # 필드 없음 -> 각 탐지기 KeyError, 전체는 안 죽음
def test_pipeline_dedupes():
    el = {"url": "u", "location": "span.a", "text": "", "direct_text": "카지노 무료", "full_text": "카지노 무료",
          "style": {"display": "none", "fontSize": "16px"}, "rect": {"width": 0, "height": 0}, "eff_opacity": 1, "eff_bg": "rgb(255, 255, 255)"}
    f = run_all_detectors([el, dict(el)])
    assert [x["technique"] for x in f] == ["OFFSCREEN"]

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try: f(); print("PASS ", n)
        except Exception as e: bad += 1; print("FAIL ", n, "->", type(e).__name__, e)
    print(f"\n{len(tests)-bad}/{len(tests)} passed")