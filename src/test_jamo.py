"""jamo.py 와 같은 폴더에서 실행: python test_jamo.py
(homoglyph.py 도 같은 폴더에 있어야 함)"""
import unicodedata

import homoglyph
from jamo import compose_jamo, detect_jamo, detect_jamo_in_elements


# ---------- 0. 사전 확인 ----------
def test_dictionary_has_dobak():
    # 테스트 사이트의 p.split(ㄷㅗㅂㅏㄱ)을 잡으려면 homoglyph.py 의 BANNED_KEYWORDS 에 "도박" 추가 필요
    assert "도박" in homoglyph.BANNED_KEYWORDS, "homoglyph.py 의 BANNED_KEYWORDS 에 '도박'을 추가하세요"


# ---------- 1. 재조합 ----------
def test_compose_basic():
    assert compose_jamo("ㅋㅏㅈㅣㄴㅗ") == "카지노"

def test_compose_next_initial_not_batchim():
    # ㄴ 뒤에 모음이 오면 받침이 아니라 다음 음절의 초성
    assert compose_jamo("ㅂㅗㄴㅓㅅㅡ") == "보너스"

def test_compose_batchim_then_initial():
    assert compose_jamo("ㅁㅓㄱㅌㅟ") == "먹튀"

def test_compose_batchim_at_end():
    assert compose_jamo("ㅊㅓㅅㅊㅜㅇ") == "첫충"

def test_compose_double_same_consonant():
    assert compose_jamo("ㅅㅡㄹㄹㅗㅅ") == "슬롯"
    assert compose_jamo("ㅎㅗㄹㄷㅓㅁ") == "홀덤"

def test_compose_partial_decomposition():
    assert compose_jamo("카ㅈㅣ노") == "카지노"

def test_compose_nfd_conjoining():
    assert compose_jamo(unicodedata.normalize("NFD", "카지노")) == "카지노"

def test_compose_leaves_laughter_alone():
    assert compose_jamo("ㅋㅋㅋ ㅎㅎ ㅠㅠ") == "ㅋㅋㅋ ㅎㅎ ㅠㅠ"

def test_compose_does_not_cross_space():
    assert compose_jamo("ㅋㅏ ㅈㅣ") == "카 지"

def test_compose_untouched_text():
    assert compose_jamo("정상 문장 abc 123") == "정상 문장 abc 123"


# ---------- 2. 탐지 ----------
def test_detect_real_site_case():
    raw = "ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7"
    r = detect_jamo(raw)
    assert r is not None
    assert "카지노" in r["matched_keywords"]
    assert r["evidence_text"] == raw

def test_detect_batchim_keyword():
    assert "먹튀" in detect_jamo("ㅁㅓㄱㅌㅟ 검증 사이트")["matched_keywords"]

def test_detect_nfd_form():
    assert detect_jamo(unicodedata.normalize("NFD", "카지노 가입 안내")) is not None

def test_ignore_laughter():
    assert detect_jamo("ㅋㅋㅋ ㅎㅎ 너무 웃기다 ㅠㅠ") is None

def test_ignore_decomposed_non_keyword():
    assert detect_jamo("ㅇㅏㄴㄴㅕㅇ ㅎㅏㅅㅔㅇㅛ") is None

def test_ignore_plain_keyword():
    assert detect_jamo("카지노 가입 안내") is None

def test_ignore_normal_text():
    assert detect_jamo("정상 본문입니다. 이용에 참고하시기 바랍니다.") is None


# ---------- 3. 요소 리스트 -> findings ----------
def _el(url, loc, direct, full=None):
    return {"url": url, "location": loc, "direct_text": direct, "full_text": direct if full is None else full}

def test_elements_direct_text():
    els = [
        _el("u", "p.desc", "ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드"),
        _el("u", "p.desc", "ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드"),   # 같은 요소 중복
        _el("u", "p.ok", "정상 문구"),
        _el("u", "p.empty", ""),
    ]
    f = detect_jamo_in_elements(els)
    assert [x["location"] for x in f] == ["p.desc"]
    assert f[0]["technique"] == "JAMO" and f[0]["is_violation"] is True

def test_elements_split_spans_deepest_only():
    els = [
        _el("u", "div.wrap", "", "ㄷㅗㅂㅏㄱ"),                          # 조상 (버려야 함)
        _el("u", "div.wrap > p.split", "", "ㄷㅗㅂㅏㄱ"),               # 정답
        _el("u", "div.wrap > p.split > span:nth-of-type(1)", "ㄷ"),
        _el("u", "div.wrap > p.split > span:nth-of-type(2)", "ㅗ"),
        _el("u", "div.wrap > p.split > span:nth-of-type(3)", "ㅂ"),
        _el("u", "div.wrap > p.split > span:nth-of-type(4)", "ㅏ"),
        _el("u", "div.wrap > p.split > span:nth-of-type(5)", "ㄱ"),
    ]
    f = detect_jamo_in_elements(els)
    assert [x["location"] for x in f] == ["div.wrap > p.split"]

def test_elements_keep_own_direct_hit_even_with_flagged_child():
    els = [
        _el("u", "p.a", "ㅋㅏㅈㅣㄴㅗ", "ㅋㅏㅈㅣㄴㅗ ㄷㅗㅂㅏㄱ"),
        _el("u", "p.a > span.b", "ㄷㅗㅂㅏㄱ"),
    ]
    locs = sorted(x["location"] for x in detect_jamo_in_elements(els))
    assert locs == ["p.a", "p.a > span.b"]

def test_elements_prefix_rule_is_per_url():
    els = [
        _el("u1", "div.wrap", "", "ㄷㅗㅂㅏㄱ"),
        _el("u2", "div.wrap > p", "ㄷㅗㅂㅏㄱ"),
    ]
    locs = sorted((x["url"], x["location"]) for x in detect_jamo_in_elements(els))
    assert locs == [("u1", "div.wrap"), ("u2", "div.wrap > p")]

def test_elements_missing_fields_raise():
    try:
        detect_jamo_in_elements([{"url": "u", "location": "l", "direct_text": "x"}])   # full_text 없음
    except KeyError:
        return
    raise AssertionError("full_text 가 없으면 KeyError 가 나야 한다")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}  ->  {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")