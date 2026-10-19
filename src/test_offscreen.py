from offscreen import detect_offscreen, detect_offscreen_in_elements

KW = "카지노 무료 쿠폰"
OK_RECT = {"width": 100, "height": 20, "top": 50, "left": 10, "right": 110, "bottom": 70}
ZERO = {"width": 0, "height": 0, "top": 0, "left": 0, "right": 0, "bottom": 0}

def S(**kw):
    base = {"display": "inline", "fontSize": "16px", "position": "static", "left": "auto", "top": "auto",
            "textIndent": "0px", "transform": "none", "clip": "auto", "clipPath": "none"}
    base.update(kw); return base

def _el(url, loc, text, style=None, rect=None):
    return {"url": url, "location": loc, "direct_text": text, "style": style or S(), "rect": rect or OK_RECT}

def test_left_minus_9999():
    r = detect_offscreen(KW, S(position="absolute", left="-9999px"), {**OK_RECT, "left": -9999, "right": -9899})
    assert r and any("left" in x for x in r["reasons"])
def test_top_minus_9999():
    assert detect_offscreen(KW, S(position="absolute", top="-9999px"))
def test_font_size_zero():
    assert detect_offscreen(KW, S(fontSize="0px"), {**OK_RECT, "width": 0, "height": 0})
def test_font_size_one():
    assert detect_offscreen(KW, S(fontSize="1px"), {**OK_RECT, "width": 9, "height": 1})
def test_font_size_two_is_not_flagged():
    assert detect_offscreen(KW, S(fontSize="2px")) is None
def test_display_none_self():
    assert detect_offscreen(KW, S(display="none"), ZERO)
def test_display_none_ancestor():
    r = detect_offscreen(KW, S(), ZERO)
    assert r and "display:none(ancestor)" in r["reasons"]
def test_child_of_offscreen_parent_by_rect():
    assert detect_offscreen(KW, S(), {**OK_RECT, "left": -9999, "right": -9899})
# 아래 방식들은 모집요강 OFFSCREEN 정의(font-size 0~1px / left:-9999px 류 / display:none)에 없다 → result.json 에는 넣지 않는다.
# (주최 측 답변 기준. 대신 extra.py 가 result_extra.json 의 ETC 로 낸다 → test_extra.py)
def test_text_indent_is_not_basic_offscreen():
    assert detect_offscreen(KW, S(textIndent="-9999px")) is None
def test_transform_translate_is_not_basic_offscreen():
    assert detect_offscreen(KW, S(transform="matrix(1, 0, 0, 1, -9999, 0)")) is None
def test_transform_pushed_rect_is_not_basic_offscreen():
    assert detect_offscreen(KW, S(transform="matrix(1, 0, 0, 1, -9999, 0)"), {**OK_RECT, "left": -9999, "right": -9899}) is None
def test_clip_rect_zero_is_not_basic_offscreen():
    assert detect_offscreen(KW, S(clip="rect(0px, 0px, 0px, 0px)")) is None
def test_clip_path_inset_is_not_basic_offscreen():
    assert detect_offscreen(KW, S(clipPath="inset(100%)")) is None
def test_one_px_box_is_not_basic_offscreen():
    assert detect_offscreen(KW, S(overflow="hidden"), {**OK_RECT, "width": 1, "height": 1}) is None
def test_zero_height_box_without_overflow_not_flagged():
    assert detect_offscreen(KW, S(), {**OK_RECT, "height": 0}) is None
def test_normal_visible_text():
    assert detect_offscreen(KW, S()) is None
def test_skip_nav_without_keyword_not_flagged():
    assert detect_offscreen("본문 바로가기", S(position="absolute", left="-9999px"), {**OK_RECT, "left": -9999, "right": -9899}) is None
def test_hidden_without_keyword_not_flagged():
    assert detect_offscreen("안녕하세요", S(display="none"), ZERO) is None
def test_small_negative_left_ok():
    assert detect_offscreen(KW, S(position="absolute", left="-20px")) is None
def test_empty_text():
    assert detect_offscreen("  ", S(display="none"), ZERO) is None
def test_adult_and_loan_phrases():
    assert detect_offscreen("성인 만남 채팅 바로가기", S(fontSize="0px"), ZERO)
    assert detect_offscreen("불법 대출 당일 승인", S(fontSize="1px"), {**OK_RECT, "height": 1})
def test_returns_original_text():
    r = detect_offscreen(KW, S(display="none"), ZERO)
    assert r["evidence_text"] == KW and "카지노" in r["matched_keywords"]
def test_elements_basic_and_dedupe():
    els = [_el("u", "span.a", KW, S(display="none"), ZERO), _el("u", "span.a", KW, S(display="none"), ZERO),
           _el("u", "span.ok", KW)]
    f = detect_offscreen_in_elements(els)
    assert [x["location"] for x in f] == ["span.a"]
    assert f[0]["technique"] == "OFFSCREEN" and f[0]["is_violation"] is True
def test_elements_same_location_different_url_kept():
    els = [_el("u1", "span.a", KW, S(display="none"), ZERO), _el("u2", "span.a", KW, S(display="none"), ZERO)]
    assert len(detect_offscreen_in_elements(els)) == 2
def test_elements_wrapper_without_direct_text_skipped():
    assert detect_offscreen_in_elements([_el("u", "div.w", "", S(display="none"), ZERO)]) == []
def test_elements_missing_fields_raise():
    for bad in ({"url": "u", "location": "l", "style": {}, "rect": {}},
                {"url": "u", "location": "l", "direct_text": "x", "rect": {}},
                {"url": "u", "location": "l", "direct_text": "x", "style": {}}):
        try:
            detect_offscreen_in_elements([bad])
        except KeyError:
            continue
        raise AssertionError("필드가 없으면 KeyError")

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for n, f in tests:
        try: f(); print("PASS ", n)
        except Exception as e: failed += 1; print("FAIL ", n, "->", type(e).__name__, e)
    print(f"\n{len(tests)-failed}/{len(tests)} passed")


def test_hidden_container_with_two_children_reports_each_element():
    # 주최 측 답변: 은닉된 상위 요소 안에 광고 문구 하위 요소가 2개면 2건(요소별). 상위 컨테이너 1건이면 나머지는 미검출.
    els = [_el("http://a/", "div.hide > p:nth-of-type(1)", KW, S(), ZERO),
           _el("http://a/", "div.hide > p:nth-of-type(2)", "바카라 필승법", S(), ZERO),
           _el("http://a/", "div.hide", "", S(display="none"), ZERO)]          # 컨테이너 자체는 직접 텍스트가 없다
    out = detect_offscreen_in_elements(els)
    assert [f["location"] for f in out] == ["div.hide > p:nth-of-type(1)", "div.hide > p:nth-of-type(2)"]
