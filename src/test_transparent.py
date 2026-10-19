"""transparent.py 와 같은 폴더에서 실행: python test_transparent.py
(homoglyph.py 도 같은 폴더에 있어야 함)

크롤러 v2 가 새로 수집하는 값을 쓴다.
  eff_opacity : 자기 opacity x 모든 조상 opacity   (부모가 opacity:0 이면 자식도 0)
  eff_bg      : 자기부터 올라가며 처음 만나는 '불투명한' 배경색 (없으면 흰색)
"""
from transparent import detect_transparent, detect_transparent_in_elements

KW = "카지노 무료 쿠폰 지급"      # 금칙어(카지노)가 들어 있는 문구
BLACK, WHITE = "rgb(0, 0, 0)", "rgb(255, 255, 255)"


def style(**kw):
    base = {"opacity": "1", "color": BLACK, "backgroundColor": "rgba(0, 0, 0, 0)",
            "display": "inline", "visibility": "visible", "fontSize": "16px",
            "position": "static", "left": "auto"}
    base.update(kw)
    return base


def det(text=KW, eff_opacity=1.0, eff_bg=WHITE, **st):
    return detect_transparent(text, style(**st), eff_opacity, eff_bg)


# ---------- 1. 잡아야 하는 것 ----------
def test_color_transparent():
    # 테스트 사이트의 span.t-transparent : color 가 rgba(0, 0, 0, 0) 로 찍힌다
    assert det(color="rgba(0, 0, 0, 0)") is not None

def test_own_opacity_zero():
    assert det(opacity="0", eff_opacity=0.0) is not None

def test_ancestor_opacity_zero():
    # 부모가 opacity:0. 자식 자신의 computed opacity 는 1 이지만 eff_opacity 는 0
    assert det(opacity="1", eff_opacity=0.0) is not None

def test_same_color_as_ancestor_background():
    # 테스트 사이트의 span.same-color : 자기 배경은 투명, 흰 배경은 부모 div 에 있다
    assert det(color=WHITE, backgroundColor="rgba(0, 0, 0, 0)", eff_bg=WHITE) is not None

def test_nearly_same_color():
    assert det(color="rgb(254, 254, 254)", eff_bg=WHITE) is not None

def test_returns_original_text_and_keywords():
    r = det(color="rgba(0, 0, 0, 0)")
    assert r["evidence_text"] == KW and "카지노" in r["matched_keywords"]


# ---------- 2. 잡으면 안 되는 것 ----------
def test_ignore_normal_visible_text():
    assert det() is None

def test_ignore_white_text_on_dark_background():
    assert det(color=WHITE, eff_bg=BLACK) is None

def test_ignore_light_gray_on_white():
    # 흐린 회색은 정상적인 디자인. 같은 색이 아니면 걸리면 안 된다
    assert det(color="rgb(204, 204, 204)", eff_bg=WHITE) is None

def test_ignore_font_size_zero():
    # font-size:0 은 명세상 OFFSCREEN 기법이다. TRANSPARENT 로 내보내면 오탐
    assert det(fontSize="0px") is None

def test_ignore_font_size_one():
    assert det(fontSize="1px") is None

def test_ignore_display_none():
    assert det(display="none") is None

def test_ignore_offscreen_position():
    assert det(position="absolute", left="-9999px") is None

def test_hidden_text_without_banned_keyword_is_not_flagged():
    # 현재 설계: 금칙어가 있어야 판정한다. (스크린리더용 정상 숨김 문구 오탐을 막기 위한 선택)
    assert det(text="본문 바로가기", opacity="0", eff_opacity=0.0) is None

def test_visibility_hidden_is_not_basic_transparent():
    # 주최 측 답변: visibility:hidden 은 기본 4종 정답이 아니다 → ETC(extra.py) 로 낸다
    assert det(visibility="hidden") is None


# ---------- 3. 요소 리스트 -> findings ----------
def _el(loc, direct=KW, url="u", **kw):
    e = {"url": url, "location": loc, "direct_text": direct, "style": style(color="rgba(0, 0, 0, 0)"),
         "eff_opacity": 1.0, "eff_bg": WHITE}
    e.update(kw)
    return e

def test_elements_basic_fields():
    f = detect_transparent_in_elements([_el("p.a")])
    assert len(f) == 1
    assert f[0]["technique"] == "TRANSPARENT" and f[0]["is_violation"] is True
    assert f[0]["evidence_text"] == KW and f[0]["location"] == "p.a" and f[0]["url"] == "u"

def test_elements_dedupe():
    assert len(detect_transparent_in_elements([_el("p.a"), _el("p.a")])) == 1

def test_elements_same_location_different_url_kept():
    assert len(detect_transparent_in_elements([_el("p.a", url="u1"), _el("p.a", url="u2")])) == 2

def test_elements_wrapper_without_direct_text_skipped():
    assert detect_transparent_in_elements([_el("div.wrap", direct="")]) == []

def test_elements_missing_direct_text_raises():
    e = _el("p.a"); del e["direct_text"]
    _must_raise_keyerror(e)

def test_elements_missing_eff_fields_raises():
    # 크롤러 v2 로 dump 를 새로 만들지 않았다면 여기서 조용히 0건이 아니라 에러가 나야 한다
    for k in ("eff_opacity", "eff_bg"):
        e = _el("p.a"); del e[k]
        _must_raise_keyerror(e)

def _must_raise_keyerror(e):
    try:
        detect_transparent_in_elements([e])
    except KeyError:
        return
    raise AssertionError("필드가 없으면 KeyError 가 나야 한다")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as ex:
            failed += 1
            print(f"FAIL  {name}  ->  {type(ex).__name__}: {ex}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
