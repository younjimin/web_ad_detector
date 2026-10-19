"""금칙어 사전과 매칭 규칙 (오프라인, 외부 API 없음).

구조
 - strong : 하나만 나와도 불법 광고로 본다 (카지노, 바카라, 비아그라 ...)
 - weak   : 단독으로는 정상 문구일 수 있어서, 같은 글에 '유도 문구(cue)'가 함께 있을 때만 인정
            (대출 + 문의/텔레그램/전화번호 등)
 - cues / soft_cues : 연락·가입·유도 표현. cues(텔레그램, URL, 전화번호, @계정 …)는 1개, soft_cues(문의, 상담, 무료 …)는 2개 이상일 때 weak 를 인정
 - exceptions : 정상 문구(성인 인증 등) 는 판정 전에 지운다
 - 띄어쓰기/특수문자/제로폭 문자를 끼워 넣은 변형('카 지 노', '카.지.노')은 3글자 이상 strong 한글 단어에 한해 잡는다

사전 갱신: 실행 파일(또는 스크립트) 옆의 banned_keywords.json 에 단어를 적으면 코드 수정·재빌드 없이 추가된다.
          환경변수 AD_DICT_PATH 로 다른 경로를 지정할 수도 있다.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_DICT: Dict[str, List[str]] = {
    "strong_ko": [
        # 도박
        "카지노", "바카라", "도박", "토토", "슬롯", "홀덤", "먹튀", "첫충", "매충", "꽁머니", "블랙잭", "파워볼",
        "사다리게임", "배팅", "베팅", "먹튀검증", "안전놀이터", "메이저사이트", "메이저놀이터", "토토사이트",
        "온라인카지노", "라이브카지노", "충환전", "총판모집", "가입쿠폰",
        # 성매매·유흥
        "조건만남", "성인만남", "출장안마", "출장마사지", "출장샵", "키스방", "안마방", "오피걸", "룸살롱", "룸싸롱",
        "성매매", "야동", "야설", "몰카", "애인대행", "불륜", "원나잇", "섹파",
        # 불법 대출·금융
        "불법대출", "당일대출", "무직자대출", "신불자", "카드깡", "통장매매", "대포통장", "작업대출", "일수대출",
        "휴대폰결제현금화", "소액결제현금화", "상품권현금화", "소액결제 현금화",
        # 불법 의약품·마약
        "비아그라", "시알리스", "레비트라", "미프진", "낙태약", "흥분제", "최음제", "필로폰", "졸피뎀",
        # 저작권·위조
        "누누티비", "불법스트리밍", "레플리카", "짝퉁", "이미테이션", "위조신분증", "위조여권",
        # 해킹·개인정보·기타
        "디도스", "계정판매", "주민번호판매", "리딩방", "주식리딩", "코인리딩",
        # 도박 (추가)
        "바둑이게임", "맞고게임", "섯다게임", "토토총판", "스포츠배팅", "카지노총판",
        # 성매매·유흥 (추가)
        "출장만남", "즉석만남", "폰팅", "여대생출장", "조건녀", "풀살롱", "립카페", "섹스파트너",
        "원조교제",
        # 불법 대출·금융 (추가)
        "무서류대출", "무방문대출", "미등록대부", "연체자대출", "신용불량자대출", "개인돈대출", "월변대출", "카드현금화",
        "통장임대", "계좌임대",
        # 의약품·마약 (추가)
        "물뽕", "히로뽕", "엑스터시", "케타민", "처방전없이",
        # 저작권·위조 (추가)
        "무료다시보기", "뉴토끼", "북토끼", "마나토끼", "티비위키", "티비몬",
        "가짜신분증", "홍콩명품", "미러급",
        # 해킹·개인정보·투자 사기 (추가)
        "개인정보판매", "디비판매", "선물리딩", "유료리딩",
        "무료리딩방",
    ],
    "strong_en": [
        "casino", "slot", "bet", "betting", "gambling", "baccarat", "roulette", "blackjack", "sportsbook",
        "jackpot", "toto", "viagra", "cialis", "levitra", "tramadol", "xanax", "porn", "payday loan",
        "sbobet", "togel", "gacor", "maxwin", "situs slot", "slot online", "judi online", "online casino", "live casino", "sports betting",
        "1xbet", "mostbet", "sildenafil", "tadalafil", "kamagra", "adderall", "oxycodone", "replica watch", "fake passport", "fake id",
    ],
    "weak_ko": [
        "대출", "성인", "만남", "채팅", "안마", "마사지", "룰렛", "포커", "경마", "사채", "급전", "일수", "정품",
        "발기", "프로포폴", "토렌트", "해킹", "도청", "감청", "위치추적", "흥신소", "알바", "부업", "고수익", "고액",
        "환전", "충전", "총판", "놀이터", "배당", "잭팟", "성인용품", "누드", "노출", "웹하드", "가품", "명품",
        "스웨디시", "유흥", "섹스", "정력제", "조루", "나비약", "펜터민", "식욕억제제",
        "온라인약국", "수익보장", "수익인증", "종목추천", "급등주", "재택알바", "재택부업",
    ],
    "weak_en": ["sex", "adult", "loan", "escort", "poker", "cheap", "pills", "pharmacy", "dating", "hookup", "bonus", "steroids", "weight loss pills", "forex signals"],
    # 강한 유도 문구: 하나만 있어도 weak 단어를 인정 (전화번호, @계정 패턴도 여기에 해당)
    "cues": [
        "텔레그램", "카톡", "카카오톡", "위챗", "라인id", "최신주소", "입금", "추천인",
        "http://", "https://", "www.", "telegram", "wechat", "whatsapp", "kakao",
        "오픈채팅", "오픈카톡", "t.me/", "bit.ly/", "open.kakao.com", "line.me", "lin.ee", "wa.me",
    ],
    # 약한 유도 문구: 정상 문구에도 흔해서, 2개 이상이거나 weak 단어가 2개 이상일 때만 인정
    "soft_cues": [
        "문의", "상담", "연락", "무료", "당일", "즉시", "가입", "지급", "바로가기", "접속", "쿠폰", "이벤트",
        "신규", "승인", "24시", "contact", "click", "join", "signup", "free", "24/7",
    ],
    "exceptions": [
        "성인 인증", "성인인증", "성인 교육", "성인교육", "성인 학습", "성인학습", "성인 대상", "미성년자",
        "청소년 유해", "본인 인증", "본인인증",
        "배팅 연습", "배팅연습", "배팅 케이지", "배팅케이지", "배팅 훈련",  # 야구 batting (의미가 다른 정상 용법)
        "time slot", "timeslot",
        # 정상 용법 (추가): 도박·성매매·마약 예방/신고 안내, 보안 공지, 고유명사
        "도박 중독", "도박중독", "도박 예방", "도박예방", "도박문제", "불법도박 신고", "불법 도박 신고", "성매매 방지", "성매매방지", "성매매 피해",
        "성매매피해", "성매매 예방", "성매매예방", "마약 예방", "마약예방", "마약류 예방", "마약 퇴치", "마약퇴치", "디도스 공격", "디도스 대응",
        "토토로",
    ],
}

# 2글자 한글 키워드(도박, 슬롯 ...)는 다른 낱말 속에 우연히 끼어 있는 경우가 많다 (타임슬롯 등).
# 낱말 앞머리에 오거나 광고에 흔한 접두어(불법, 온라인 ...) 뒤에 올 때만 인정한다.
_HANGUL = re.compile(r"[가-힣]")
SHORT_PREFIXES = ("불법", "온라인", "해외", "사설", "스포츠", "무료", "인터넷", "모바일", "라이브", "합법", "안전", "실시간",
                  "메이저", "국내", "신규", "추천", "한국", "검증", "프리미엄", "미니", "대박", "먹튀없는", "vip")


def _short_keyword_in(kw: str, low: str) -> bool:
    start = low.find(kw)
    while start != -1:
        head = low[:start]
        if not head or not _HANGUL.match(head[-1]) or head.endswith(SHORT_PREFIXES):
            return True
        start = low.find(kw, start + 1)
    return False


_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4})(?!\d)")
_HANDLE = re.compile(r"(?<![\w.])@[a-z0-9_]{4,}", re.I)
_SEP = re.compile(r"[\s\u200b-\u200f\u2060\ufeff.,\-_·•~*|/\\:;!?()\[\]{}'\"`^]+")


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class Dictionary:
    def __init__(self, data: Dict[str, List[str]]):
        g = lambda k: [w.strip().lower() for w in data.get(k, []) if w and w.strip()]
        self.strong_ko, self.strong_en = g("strong_ko"), g("strong_en")
        self.weak_ko, self.weak_en = g("weak_ko"), g("weak_en")
        self.cues, self.soft_cues, self.exceptions = g("cues"), g("soft_cues"), g("exceptions")
        self.strong_ko_compact = [w for w in self.strong_ko if len(_SEP.sub("", w)) >= 3]
        self._en_cache: Dict[str, "re.Pattern"] = {}

    def en_pattern(self, kw: str):
        p = self._en_cache.get(kw)
        if p is None:
            body = r"\s+".join(re.escape(part) for part in kw.split())
            p = re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")
            self._en_cache[kw] = p
        return p

    @property
    def strong_all(self) -> List[str]:
        return self.strong_ko + self.strong_en

    def weak_allowed(self, low: str, n_weak: int) -> bool:
        """weak 단어를 불법 광고 신호로 인정할지.
        강한 유도 문구(텔레그램/카톡/URL/전화번호/@계정) 1개, 또는 약한 유도 문구 2개,
        또는 (weak 단어 2개 이상 + 약한 유도 문구 1개)"""
        if any(c in low for c in self.cues) or _PHONE.search(low) or _HANDLE.search(low):
            return True
        soft = sum(1 for c in self.soft_cues if c in low)
        return soft >= 2 or (n_weak >= 2 and soft >= 1)

    def find(self, text: str) -> List[str]:
        """같은 문장(메뉴·푸터 등)이 페이지마다 반복되므로 결과를 캐시한다."""
        if not text:
            return []
        cache = self.__dict__.setdefault("_find_cache", {})
        hit = cache.get(text)
        if hit is None:
            hit = self._find(text)
            if len(cache) >= 200000:
                cache.clear()
            cache[text] = hit
        return list(hit)

    def _find(self, text: str) -> List[str]:
        low = text.lower()
        for ex in self.exceptions:
            low = low.replace(ex, " ")
        compact = _SEP.sub("", low)
        found: List[str] = []

        for kw in self.strong_ko:
            if len(kw) <= 2 and _HANGUL.match(kw[0]):
                if _short_keyword_in(kw, low):
                    found.append(kw)
            elif kw in low:
                found.append(kw)
            elif kw in self.strong_ko_compact and _SEP.sub("", kw) in compact:
                found.append(kw)                                  # 카 지 노 / 카.지.노 / 제로폭 문자
        for kw in self.strong_en:
            if self.en_pattern(kw).search(low):
                found.append(kw)

        weak = [kw for kw in self.weak_ko if kw in low] + [kw for kw in self.weak_en if self.en_pattern(kw).search(low)]
        if weak and self.weak_allowed(low, len(weak)):
            found.extend(weak)

        seen, out = set(), []
        for kw in found:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out


def _candidate_paths() -> List[Path]:
    paths = []
    env = os.environ.get("AD_DICT_PATH")
    if env:
        paths.append(Path(env))
    paths.append(base_dir() / "banned_keywords.json")
    return paths


def load_dictionary(extra_path: Optional[Path] = None) -> Dictionary:
    data = {k: list(v) for k, v in DEFAULT_DICT.items()}
    paths = [Path(extra_path)] if extra_path else _candidate_paths()
    for p in paths:
        try:
            if p.is_file():
                with open(p, encoding="utf-8-sig") as f:
                    extra = json.load(f)
                for k in data:
                    data[k].extend(extra.get(k, []))
                print(f"[사전] 추가 사전 적용: {p}")
                break
        except Exception as e:                                    # 사전 파일이 깨져도 기본 사전으로 계속 동작
            print(f"[!] 사전 파일을 읽지 못했습니다 ({p}): {e}")
    return Dictionary(data)


DICTIONARY = load_dictionary()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--export":
        template = {"_설명": "여기에 단어를 추가하면 재빌드 없이 사전이 확장됩니다. strong=단독 판정, weak=유도문구와 함께일 때 판정"}
        template.update({k: [] for k in DEFAULT_DICT})
        Path(sys.argv[2]).write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        print("저장:", sys.argv[2])
    else:
        for k, v in DEFAULT_DICT.items():
            print(f"{k:10} {len(v)}개")
