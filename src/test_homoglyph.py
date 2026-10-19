"""homoglyph.py 와 같은 폴더에서 실행: python test_homoglyph.py
(pytest가 있으면 pytest 로도 돌아감)

키릴 문자는 눈으로 구분이 안 되니 유니코드 이스케이프로 적어뒀다.
  \u0441 = 키릴 с   \u0430 = 키릴 а   \u0456 = 키릴 і   \u043e = 키릴 о
"""
import unicodedata

from homoglyph import (
    normalize_for_matching,
    detect_homoglyph,
    detect_homoglyph_in_elements,
)

CYR_CASINO = "\u0441\u0430s\u0456n\u043e"  # 키릴 문자가 섞인 'casino'


# ---------- 1. 정규화 ----------
def test_normalize_fullwidth():
    assert normalize_for_matching("ｍｅｇａ－ＢＥＴ") == "mega-bet"

def test_normalize_cyrillic():
    assert normalize_for_matching(CYR_CASINO) == "casino"

def test_normalize_keeps_korean():
    assert normalize_for_matching("첫충 30％ 지급") == "첫충 30% 지급"


# ---------- 2. 탐지: 잡아야 하는 것 ----------
def test_detect_fullwidth_bet():
    raw = "ｍｅｇａ－ＢＥＴ 첫충 30％ 지급"
    r = detect_homoglyph(raw)
    assert r is not None
    assert "bet" in r["matched_keywords"]
    assert r["evidence_text"] == raw          # 원문 그대로

def test_detect_cyrillic_casino():
    r = detect_homoglyph(CYR_CASINO + " 가입코드 LUCKY7")
    assert r is not None
    assert "casino" in r["matched_keywords"]

def test_detect_latin_keyword_next_to_hangul():
    # \b 로 짜면 여기서 놓친다 (한글을 단어 문자로 취급)
    assert detect_homoglyph("ＢＥＴ첫충 이벤트") is not None


def test_detect_uppercase_cyrillic_not_in_map():
    # С А Ѕ І N О : 키릴 대문자 С,А,Ѕ(U+0405),І(U+0406),О + 라틴 N
    # Ѕ, І 는 대문자 항목이 표에 없어도 lower() 뒤 2차 치환으로 잡혀야 한다
    assert normalize_for_matching("\u0421\u0410\u0405\u0406N\u041e") == "casino"

def test_detect_cyrillic_capital_bet():
    # В Е Т 모두 키릴 대문자. 대문자 항목을 지우면 이 테스트가 실패한다
    r = detect_homoglyph("\u0412\u0415\u0422 \uccab\ucda9 \uc774\ubca4\ud2b8")
    assert r is not None
    assert "bet" in r["matched_keywords"]


def test_detect_leet_digits_casino():
    r = detect_homoglyph("c4s1n0 가입코드 LUCKY7")
    assert r is not None
    assert "casino" in r["matched_keywords"]

def test_detect_leet_fullwidth_digits():
    # 전각 숫자는 NFKC 를 거친 뒤 leet 탐지에 걸려야 한다
    assert detect_homoglyph("ｃ４ｓ１ｎ０ 이벤트") is not None

def test_detect_leet_slot():
    assert "slot" in detect_homoglyph("sl0t 무료 체험")["matched_keywords"]

def test_detect_leet_next_to_hangul():
    assert detect_homoglyph("b3t첫충 이벤트") is not None

def test_detect_leet_symbols():
    assert detect_homoglyph("c@s!n0 오픈") is not None


# ---------- 3. 탐지: 잡으면 안 되는 것 (오탐 방지) ----------
def test_ignore_normal_text():
    assert detect_homoglyph("정상 본문입니다. 이용에 참고하시기 바랍니다.") is None

def test_ignore_plain_keyword_without_disguise():
    # 위장 없이 그냥 쓴 평문 광고는 HOMOGLYPH 가 아님
    assert detect_homoglyph("카지노 가입 안내") is None

def test_ignore_legacy_fullwidth_digits():
    assert detect_homoglyph("２０２６년 하반기 사업 안내") is None

def test_ignore_keyword_inside_normal_word():
    # 'better' 안의 'bet' 은 금칙어가 아님
    assert detect_homoglyph("ｂｅｔｔｅｒ ｓｅｒｖｉｃｅ") is None


def test_ignore_pure_numbers():
    # '837' 은 숫자만 보면 b-e-t 로 읽히지만 영문자가 하나도 없으므로 기각
    assert detect_homoglyph("문의 837-7777 / 2026-10-11") is None

def test_ignore_room_code():
    # 'B37' : 영문 1개 + 숫자 2개 -> 기각
    assert detect_homoglyph("B37호 회의실 안내") is None

def test_ignore_keyword_followed_by_digits():
    assert detect_homoglyph("bet2026 보고서") is None

def test_ignore_common_codes():
    assert detect_homoglyph("A4 용지, 5G 요금제, Q3 실적, 3.5mm 단자") is None


def test_ignore_jamo_decomposed_compat():
    # 실제 테스트 사이트 p.desc : 이건 JAMO 기법이지 HOMOGLYPH 가 아니다
    assert detect_homoglyph("ㅋㅏㅈㅣㄴㅗ ㅂㅗㄴㅓㅅㅡ 코드 LUCKY7") is None

def test_ignore_jamo_decomposed_nfd():
    # 조합용 자모(NFD)로 풀어 쓴 한글도 HOMOGLYPH 가 아니다
    assert detect_homoglyph(unicodedata.normalize("NFD", "카지노 가입 안내")) is None

def test_normalize_leaves_jamo_alone():
    assert normalize_for_matching("ㅋㅏㅈㅣㄴㅗ") == "ㅋㅏㅈㅣㄴㅗ"


# ---------- 4. 요소 리스트 -> findings ----------
def test_elements_to_findings():
    elements = [
        {"url": "https://a.test/p", "location": "p.x", "direct_text": CYR_CASINO + " 코드"},
        {"url": "https://a.test/p", "location": "p.x", "direct_text": CYR_CASINO + " 코드"},  # 같은 요소 중복
        {"url": "https://b.test/p", "location": "p.x", "direct_text": CYR_CASINO + " 코드"},  # 다른 페이지
        {"url": "https://a.test/p", "location": "p.y", "direct_text": "정상 문구"},
        {"url": "https://a.test/p", "location": "p.z", "direct_text": ""},                    # 직계 텍스트 없음
    ]
    findings = detect_homoglyph_in_elements(elements)
    assert len(findings) == 2                         # (url, location) 기준 1건씩
    for f in findings:
        assert f["technique"] == "HOMOGLYPH"
        assert f["is_violation"] is True
        assert {"url", "location", "evidence_text"} <= set(f)


def test_elements_missing_direct_text_raises():
    try:
        detect_homoglyph_in_elements([{"url": "u", "location": "l", "text": "x"}])
    except KeyError:
        return
    raise AssertionError("direct_text 가 없으면 KeyError 가 나야 한다")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:  # NotImplementedError 포함
            failed += 1
            print(f"FAIL  {name}  ->  {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
