import json, tempfile
from pathlib import Path
from keywords import DICTIONARY, Dictionary, DEFAULT_DICT, load_dictionary
from homoglyph import find_keywords

# 불법 광고로 판정되어야 하는 문구 (사람이 쓴 예시)
BAD = [
    "카지노 무료 쿠폰 지급", "바카라 필승 전략 텔레그램 문의", "먹튀검증 안전놀이터 상담 텔레그램 @promo_777",
    "토토 사이트 추천 가입 즉시 지급", "홀덤 포커 머니 충전 텔레그램", "무료 슬롯 체험 바로가기",
    "카 지 노 가입코드 LUCKY7", "카.지.노 최신주소", "카\u200b지\u200b노 이벤트", "온라인 바 카 라 상담",
    "성인 만남 채팅 바로가기", "조건만남 24시 상담 010-1234-5678", "출장안마 후불제 문의 카톡 abc123",
    "불법 대출 당일 승인", "무직자대출 당일 지급 문의 010 1234 5678", "당일 대출 즉시 승인 카톡 문의",
    "소액결제 현금화 최고 수수료", "카드깡 통장매매 문의", "비아그라 시알리스 정품 판매", "미프진 구매 텔레그램",
    "누누티비 대체 사이트 접속 주소", "명품 레플리카 짝퉁 최신 입고", "리딩방 수익 인증 무료 입장",
    "고액 알바 일당 지급 문의 @job_kr1", "성인용품 무료 배송 문의 http://abc.xyz",
    "Best online casino bonus telegram", "free slot machine join now", "baccarat roulette blackjack 24/7",
    "buy viagra cialis cheap pills", "payday loan approved instantly", "adult dating escort contact whatsapp",
    "도박 사이트 홍보", "BET 첫충 30% 지급", "sportsbook jackpot free bonus",
]
# 정상 문구 (공공기관 사이트에서 흔한 표현)
GOOD = [
    "본문 바로가기", "주메뉴 바로가기", "정보공개 청구 안내", "민원 상담 전화 110", "행정안전부 페이스북 새창으로 열기",
    "성인 인증이 필요합니다", "성인교육 프로그램 안내", "본인인증 후 이용해 주세요", "미성년자 접근 제한",
    "대출 상환 방법 안내", "주택담보대출 금리 공시", "정책자금 융자 신청 절차", "국고보조금 현황 공개",
    "예산 집행 현황", "개인정보 처리방침", "저작권 보호 정책", "이용약관 및 운영 정책",
    "도서관 휴관 안내", "전화번호 안내: 02-1234-5678", "담당자 문의: 02-1234-5678", "연락처 02-123-4567",
    "Skip to main content", "Contact us", "Free download of the annual report", "Join our newsletter",
    "adult education center", "student loan information", "poker face", "Essex county", "slotted screw",
    "사회복지 서비스 안내", "채팅 상담 서비스 운영 시간 안내", "충전 시설 안내", "전기차 충전소 위치",
    "마사지 의자 구매 입찰 공고", "안마 의자 조달 공고", "알바 채용 공고 (청년 인턴)", "고액 체납자 명단 공개",
    "정품 인증 방법", "노출 위험 사업장 점검", "채용 상담 문의",
    "중국 성도박범가특교육 대표단 본교 방문(MOU 체결)", "세미나 타임슬롯 안내", "야구부 배팅 연습장 이용 안내",
]

def test_short_keyword_boundary():
    # 낱말 한가운데에 들어간 2글자 키워드는 오탐 (성도박물관, 타임슬롯, 성도박범가)
    for ok in ["성도박물관 방문", "세미나 타임슬롯 안내", "중국 성도박범가특교육 대표단"]:
        assert not find_keywords(ok), ok
    # 앞머리이거나 흔한 접두어가 붙으면 인정
    for bad in ["도박 사이트 홍보", "불법도박 사이트", "온라인슬롯 이벤트", "무료 슬롯 체험 바로가기", "스포츠토토 분석", "BET 첫충 30% 지급"]:
        assert find_keywords(bad), bad

def test_bad_samples_flagged():
    missed = [t for t in BAD if not find_keywords(t)]
    assert not missed, f"놓친 문구: {missed}"

def test_good_samples_not_flagged():
    wrong = {t: find_keywords(t) for t in GOOD if find_keywords(t)}
    assert not wrong, f"오탐: {wrong}"

def test_weak_needs_cue():
    assert find_keywords("대출 안내") == []
    assert "대출" in find_keywords("대출 상담 텔레그램")

def test_one_soft_cue_is_not_enough():
    assert find_keywords("채팅 상담 서비스") == []
    assert "대출" in find_keywords("대출 상담 즉시 승인")         # soft 3개
    assert find_keywords("성인 채팅 안내") == []                   # weak 2개지만 유도 문구 없음
    assert find_keywords("성인 채팅 바로가기")                     # weak 2개 + soft 1개

def test_phone_is_a_cue():
    assert "대출" in find_keywords("대출 010-1234-5678")
    assert find_keywords("대출 02") == []

def test_handle_is_a_cue():
    assert "성인" in find_keywords("성인 @abcd_01")

def test_exception_phrases_removed():
    assert find_keywords("성인 인증 문의") == []

def test_compact_matching_only_for_strong_long_words():
    assert "카지노" in find_keywords("카 지 노")
    assert find_keywords("토 토") == []                    # 2글자는 다른 단어끼리 붙을 위험이 커서 제외

def test_zero_width_inside_word():
    assert "카지노" in find_keywords("카\u200b지\u200b노")

def test_english_boundary():
    assert find_keywords("Essex") == [] and find_keywords("embetter") == []
    assert "bet" in find_keywords("place your bet now")

def test_english_phrase_with_flexible_space():
    assert "payday loan" in find_keywords("PAYDAY   LOAN offer")

def test_returns_unique():
    r = find_keywords("카지노 카지노 카지노")
    assert r.count("카지노") == 1

def test_dictionary_size():
    n = sum(len(DEFAULT_DICT[k]) for k in ("strong_ko", "strong_en", "weak_ko", "weak_en"))
    assert n >= 120, n

def test_empty_and_none():
    assert find_keywords("") == [] and find_keywords(None) == []

def test_default_cues_are_in_lists():
    assert "텔레그램" in DEFAULT_DICT["cues"] and "문의" in DEFAULT_DICT["soft_cues"]

def test_external_json_extends_dictionary():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "banned_keywords.json"
        p.write_text(json.dumps({"strong_ko": ["테스트금칙어"], "weak_ko": ["약한단어"], "cues": ["신호"]}, ensure_ascii=False), encoding="utf-8")
        dic = load_dictionary(p)
        assert dic.find("테스트금칙어") == ["테스트금칙어"]
        assert dic.find("약한단어") == [] and dic.find("약한단어 신호") == ["약한단어"]
        assert "카지노" in dic.find("카지노")             # 기본 사전은 그대로 유지

def test_broken_json_falls_back_to_default():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "banned_keywords.json"
        p.write_text("{ 깨진 json", encoding="utf-8")
        assert "카지노" in load_dictionary(p).find("카지노")

def test_bom_json_ok():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "banned_keywords.json"
        p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"strong_ko": ["비엠원"]}, ensure_ascii=False).encode("utf-8"))
        assert load_dictionary(p).find("비엠원")

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try: f(); print("PASS ", n)
        except Exception as e: bad += 1; print("FAIL ", n, "->", type(e).__name__, e)
    print(f"\n{len(tests)-bad}/{len(tests)} passed")
