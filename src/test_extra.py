from extra import detect_extra, detect_extra_in_elements
from offscreen import offscreen_reasons

KW = "카지노 무료 쿠폰"
OK_RECT = {"width": 100, "height": 20, "top": 50, "left": 10, "right": 110, "bottom": 70}


def S(**kw):
    base = {"opacity": "1", "color": "rgb(0, 0, 0)", "backgroundColor": "rgba(0, 0, 0, 0)", "display": "inline",
            "visibility": "visible", "fontSize": "16px", "position": "static", "left": "auto", "top": "auto",
            "textIndent": "0px", "transform": "none", "overflow": "visible", "clip": "auto", "clipPath": "none"}
    base.update(kw)
    return base


def names(text=KW, style=None, rect=None):
    return [n for n, _ in detect_extra(text, style or S(), rect or OK_RECT)]


def test_visibility_hidden():
    assert names(style=S(visibility="hidden")) == ["visibility:hidden 은닉"]

def test_clip_rect():
    assert names(style=S(clip="rect(0px, 0px, 0px, 0px)")) == ["clip 잘라내기 은닉"]

def test_clip_path():
    assert names(style=S(clipPath="inset(100%)")) == ["clip 잘라내기 은닉"]

def test_one_px_box_with_overflow_hidden():
    assert names(style=S(overflow="hidden"), rect={**OK_RECT, "width": 1, "height": 1}) == ["1px 상자+overflow:hidden 은닉"]

def test_one_px_box_without_overflow_hidden_is_not_flagged():
    assert names(rect={**OK_RECT, "width": 1, "height": 1}) == []

def test_one_px_font_size_is_basic_not_box():
    # 글자 크기 1px 은 기본 OFFSCREEN 의 몫 (주최 측: 상자 1px 과 font-size:1px 은 구분)
    assert offscreen_reasons(S(fontSize="1px"), OK_RECT)
    assert names(style=S(fontSize="1px", overflow="hidden"), rect={**OK_RECT, "width": 1, "height": 1}) == []

def test_text_indent_and_transform():
    assert names(style=S(textIndent="-9999px")) == ["text-indent 화면 밖 은닉"]
    assert names(style=S(transform="matrix(1, 0, 0, 1, -9999, 0)")) == ["transform 화면 밖 은닉"]

def test_zero_width_characters():
    assert names(text="카​지​노 무료 쿠폰") == ["제로폭 문자 삽입"]

def test_visible_text_not_flagged():
    assert names() == []

def test_no_keyword_not_flagged():
    assert names(text="본문 바로가기", style=S(visibility="hidden")) == []

def test_zero_by_zero_rect_stays_basic_display_none():
    z = {"width": 0, "height": 0, "top": 0, "left": 0, "right": 0, "bottom": 0}
    assert names(style=S(overflow="hidden"), rect=z) == []
    assert "display:none(ancestor)" in offscreen_reasons(S(overflow="hidden"), z)

def _el(loc, text=KW, style=None):
    return {"url": "http://a/", "location": loc, "direct_text": text, "style": style or S(), "rect": OK_RECT}

def test_elements_skip_ones_already_found_as_basic():
    els = [_el("p.a", style=S(visibility="hidden")), _el("p.b", style=S(visibility="hidden"))]
    basic = [{"url": "http://a/", "location": "p.a", "technique": "TRANSPARENT"}]
    out = detect_extra_in_elements(els, basic)
    assert [f["location"] for f in out] == ["p.b"]
    assert out[0]["technique"] == "ETC" and out[0]["extra_finding"] == "visibility:hidden 은닉"

def test_elements_dedupe():
    els = [_el("p.a", style=S(visibility="hidden")), _el("p.a", style=S(visibility="hidden"))]
    assert len(detect_extra_in_elements(els, [])) == 1
