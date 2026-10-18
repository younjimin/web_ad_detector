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
    ],
    "strong_en": [
        "casino", "slot", "bet", "betting", "gambling", "baccarat", "roulette", "blackjack", "sportsbook",
        "jackpot", "toto", "viagra", "cialis", "levitra", "tramadol", "xanax", "porn", "payday loan",
    ],
    "weak_ko": [
        "대출", "성인", "만남", "채팅", "안마", "마사지", "룰렛", "포커", "경마", "사채", "급전", "일수", "정품",
        "발기", "프로포폴", "토렌트", "해킹", "도청", "감청", "위치추적", "흥신소", "알바", "부업", "고수익", "고액",
        "환전", "충전", "총판", "놀이터", "배당", "잭팟", "성인용품", "누드", "노출", "웹하드", "가품", "명품",
    ],
    "weak_en": ["sex", "adult", "loan", "escort", "poker", "cheap", "pills", "pharmacy", "dating", "hookup", "bonus"],
    # 강한 유도 문구: 하나만 있어도 weak 단어를 인정 (전화번호, @계정 패턴도 여기에 해당)
    "cues": [
        "텔레그램", "카톡", "카카오톡", "위챗", "라인id", "최신주소", "입금", "추천인",
        "http://", "https://", "www.", "telegram", "wechat", "whatsapp", "kakao",
    ],
    # 약한 유도 문구: 정상 문구에도 흔해서, 2개 이상이거나 weak 단어가 2개 이상일 때만 인정
    "soft_cues": [
        "문의", "상담", "연락", "무료", "당일", "즉시", "가입", "지급", "바로가기", "접속", "쿠폰", "이벤트",
        "신규", "승인", "24시", "contact", "click", "join", "signup", "free", "24/7",
    ],
    "exceptions": [
        "성인 인증", "성인인증", "성인 교육", "성인교육", "성인 학습", "성인학습", "성인 대상", "미성년자",
        "청소년 유해", "본인 인증", "본인인증",
    ],
}

_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4})(?!\d)")
_HANDLE = re.compile(r"(?<![\w.])@[a-z0-9_]{4,}", re.I)
_SEP = re.compile(r"[\s​-‏⁠﻿.,\-_·•~*|/\\:;!?()\[\]{}'\"`^]+")


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
        if not text:
            return []
        low = text.lower()
        for ex in self.exceptions:
            low = low.replace(ex, " ")
        compact = _SEP.sub("", low)
        found: List[str] = []

        for kw in self.strong_ko:
            if kw in low:
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