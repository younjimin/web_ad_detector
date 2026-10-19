# 서리누리 (Seorinuri)

[한국어](#한국어) · [English](#english)

---

## 한국어

공공 웹사이트를 돌아다니며, 사람 눈에는 보이지 않지만 검색 로봇에는 읽히는 불법 광고 문구를 찾아내는 Windows 프로그램입니다. 행정안전부·한국지능정보사회진흥원 「공공 웹사이트 불법광고 탐지 도구 개발 공모전」 출품작입니다.

크롤링을 제외하면 오프라인으로 동작합니다. 외부 API나 클라우드 서비스를 쓰지 않고, 프로그램에 내장된 금칙어 사전과 규칙으로 판정합니다.

### 탐지 대상

공모전이 정의한 4가지 기법입니다.

| 기법 | 찾는 것 |
|---|---|
| `HOMOGLYPH` | 키릴·그리스·전각 문자나 숫자·기호로 금칙어를 흉내 낸 글자 |
| `JAMO` | 한글을 자모로 쪼갠 글자 (`ㅋㅏㅈㅣㄴㅗ`) |
| `TRANSPARENT` | `opacity:0`, `color:transparent`, 배경과 같은 색으로 숨긴 텍스트 |
| `OFFSCREEN` | 글자 크기 0~1px, `position` 으로 화면 밖에 밀어낸 텍스트, `display:none` |

금칙어가 함께 있을 때만 결과에 남깁니다. 숨겨져 있어도 금칙어가 없는 텍스트(건너뛰기 링크 등)는 무시합니다.

기본 4종 밖의 숨김 방식은 `result_extra.json` 에 `ETC` 로 따로 저장합니다. `visibility:hidden`, `clip` / `clip-path`, 1px 이하 상자 + `overflow:hidden`, `text-indent` · `transform` 으로 화면 밖에 둔 경우, 글자 사이에 제로폭 문자를 끼워 넣은 경우입니다. 기본 4종에 이미 걸린 요소는 다시 내지 않습니다.

### 결과 파일

탐지가 끝나면 실행 파일(또는 소스로 실행할 때는 `scan_core.py`)이 있는 폴더에 세 파일이 만들어집니다.

- `result.json`: 기본 4종 탐지 결과 (공모전 표준 스키마)
- `result_extra.json`: 추가 탐지(`ETC`) 결과
- `report.html`: 브라우저로 여는 단독 리포트

각 항목에는 페이지 URL, 요소 하나만 가리키는 CSS 선택자(iframe 안은 `iframe[src="..."] >>> 선택자`), 근거 원문이 들어갑니다.

### 사용법

**Windows 실행 파일**

압축을 풀고 `Seorinuri.exe` 를 실행합니다. 시작 URL을 넣고 탐지 시작을 누르면 됩니다. 크롤링은 최대 23분이라 전체 실행이 30분 안에 끝납니다. 자세한 내용은 사용설명서를 봐 주세요.

**소스로 실행**

빌드는 Python 3.11 기준입니다.

```
pip install -r requirements-dev.txt
python -m playwright install --only-shell chromium
python src/main.py https://example.go.kr
```

URL 없이 `src/main.py` 를 실행하면 화면(GUI)이 열립니다.

**테스트**

```
cd src
python -m pytest -q
```

**exe 빌드**

Windows 빌드는 GitHub Actions(`.github/workflows/build.yml`)에서 돌아갑니다. 단위 테스트, PyInstaller(`--onedir`, Chromium 포함), 로컬 테스트 페이지로 스모크 테스트 순서입니다. 직접 빌드하려면 다음과 같이 합니다.

```
pyinstaller --noconfirm --onedir --console --name "Seorinuri" --paths src --collect-all playwright src/main.py
```

### 금칙어 사전 확장

실행 파일 옆에 `banned_keywords.json` 을 두면 시작할 때 내장 사전과 합쳐집니다. 다시 빌드할 필요가 없습니다. 템플릿은 다음 명령으로 만듭니다.

```
python src/keywords.py --export banned_keywords.json
```

키는 `strong_ko`, `strong_en`(단독으로 탐지), `weak_ko`, `weak_en`(텔레그램 아이디·URL·전화번호 같은 유도 문구와 함께 있을 때만 탐지), `cues`, `soft_cues`, `exceptions` 입니다. 환경 변수 `AD_DICT_PATH` 로 다른 파일을 지정할 수도 있습니다.

### 구성

```
src/
  main.py            진입점 (CLI / GUI)
  gui.py             Tkinter 화면
  scan_core.py       크롤링 -> 탐지 -> 파일 저장
  crawler.py         Playwright 크롤러 (텍스트 노드와 계산된 스타일 수집)
  pipeline.py        탐지기 실행
  homoglyph.py  jamo.py  transparent.py  offscreen.py   기본 4종 탐지기
  extra.py           ETC 탐지기
  keywords.py        금칙어 사전과 매칭 규칙
  result_writer.py   result.json / result_extra.json
  report.py          report.html
  verify_selectors.py  선택자가 요소 하나만 가리키는지 검사
  eval_v2.py         test_site_v2/expected.json 과 비교해 채점
  test_*.py          단위 테스트
test_site/  test_site_v2/   숨김 문구를 직접 넣어 만든 테스트 페이지
.github/workflows/build.yml
```

### 크롤러 동작

- Playwright(Chromium), 탭 4개 병렬, 같은 도메인 링크만, 최대 1000페이지.
- URL 패턴별로 고르게 방문해서, 게시판처럼 글이 수천 개인 구역이 페이지 수를 독점하지 못합니다.
- `robots.txt` 를 읽지 않고 요청 간격도 조절하지 않습니다. 점검을 허가받은 사이트에서만 쓰세요.

### 정확도

공모전 사이트의 정답 데이터가 없어서, 아래 수치는 이 저장소에 직접 만들고 정답을 표시한 테스트 페이지 기준입니다. 설계한 대로 동작한다는 뜻이지 실제 사이트에서의 성능은 아닙니다.

- `test_site_v2`: 표시한 12건 중 12건 탐지, 오탐 0건
- 공모전 테스트 키트: 13건 탐지

한계: 사전에 없는 단어는 찾지 못합니다. 이미지나 canvas 에 그려진 글자는 범위 밖입니다. `text-indent` · `transform` 으로 화면 밖에 둔 경우를 기본 `OFFSCREEN` 으로 볼지 `ETC` 로 볼지는 공모전 정의를 제가 해석한 것입니다.

### 확장 가능성

모호한 문구의 판정을 돕는 모델 기반 분류기를 사전 단계 뒤에 붙일 수 있습니다. 이 버전은 외부 서비스 없이 동작하도록 일부러 넣지 않았습니다.

---

## English

A Windows tool that crawls a public-sector website and finds advertising text hidden from human readers but visible to search engines and bots. Entry for the 2026 MOIS / NIA contest "Illegal Advertisement Detection Tool for Public Websites".

It runs fully offline apart from the crawl itself: no external APIs, no cloud services. Detection is rule-based, with a keyword dictionary that ships with the tool.

### What it detects

The four techniques defined by the contest:

| Technique | What it looks for |
|---|---|
| `HOMOGLYPH` | Look-alike characters (Cyrillic/Greek/full-width letters, leet digits) used to spell banned words |
| `JAMO` | Hangul syllables split into separate jamo (`ㅋㅏㅈㅣㄴㅗ`) to dodge keyword filters |
| `TRANSPARENT` | Text with `opacity:0`, `color:transparent`, or the same color as its background |
| `OFFSCREEN` | Text with font-size 0-1px, pushed far off-screen with `position`, or `display:none` |

A banned keyword must be present for a finding to be reported. Text that is merely hidden (skip-navigation links, for example) is ignored.

Techniques outside the contest definition are reported separately as `ETC` in `result_extra.json`: `visibility:hidden`, `clip` / `clip-path`, 1px boxes with `overflow:hidden`, `text-indent` and `transform` shifts, and zero-width characters inserted between letters. An element already reported under the four main techniques is not repeated there.

### Output

Each scan writes three files next to the executable (or next to `scan_core.py` when run from source):

- `result.json`: findings for the four main techniques, in the contest schema
- `result_extra.json`: `ETC` findings
- `report.html`: a self-contained report you can open in any browser

Each finding carries the page URL, a CSS selector that matches exactly one element (iframe content is addressed as `iframe[src="..."] >>> selector`), and the original text.

### Usage

**Windows executable**

Unzip the release and run `Seorinuri.exe`. Enter a start URL, press start, and open the report when it finishes. A scan is capped at 23 minutes of crawling so the whole run stays under 30 minutes. See the user manual for details.

**From source**

Python 3.11 is what the build uses.

```
pip install -r requirements-dev.txt
python -m playwright install --only-shell chromium
python src/main.py https://example.go.kr
```

Running `src/main.py` without a URL starts the GUI.

**Tests**

```
cd src
python -m pytest -q
```

**Building the executable**

The Windows build runs on GitHub Actions (`.github/workflows/build.yml`): tests, then PyInstaller (`--onedir`, Chromium bundled), then a smoke test against a local test page. To build by hand:

```
pyinstaller --noconfirm --onedir --console --name "Seorinuri" --paths src --collect-all playwright src/main.py
```

### Extending the dictionary

Put a `banned_keywords.json` next to the executable. It is merged with the built-in dictionary at startup, so no rebuild is needed. Generate a template with:

```
python src/keywords.py --export banned_keywords.json
```

Keys: `strong_ko`, `strong_en` (reported on their own), `weak_ko`, `weak_en` (reported only alongside a contact/invitation phrase such as a Telegram handle, URL or phone number), `cues`, `soft_cues`, `exceptions`. The `AD_DICT_PATH` environment variable points to a different file.

### Layout

```
src/
  main.py            entry point (CLI / GUI)
  gui.py             Tkinter front end
  scan_core.py       crawl -> detect -> write files
  crawler.py         Playwright crawler, collects text nodes with computed styles
  pipeline.py        runs the detectors
  homoglyph.py  jamo.py  transparent.py  offscreen.py   main detectors
  extra.py           ETC detector
  keywords.py        dictionary and matching rules
  result_writer.py   result.json / result_extra.json
  report.py          report.html
  verify_selectors.py  checks that every selector matches one element
  eval_v2.py         scores a run against test_site_v2/expected.json
  test_*.py          unit tests
test_site/  test_site_v2/   hand-made pages with known hidden text
.github/workflows/build.yml
```

### Crawler behavior

- Playwright (Chromium), 4 parallel tabs, same-domain links only, up to 1000 pages.
- Pages are visited fairly across URL patterns, so one huge section (a bulletin board with thousands of posts, say) cannot use up the page budget.
- The crawler does not read `robots.txt` and does not throttle requests. Use it only on sites you are authorized to scan.

### Accuracy

I have no ground-truth data from the contest sites. The numbers below come from the test pages in this repository, which I labelled myself, so they say the detectors do what I designed them to do, not how they will do on real sites:

- `test_site_v2`: 12 of 12 labelled items found, 0 false positives
- the contest test kit: 13 findings

Known limits: the dictionary is finite, and a keyword that is not in it is not found. Text rendered into images or canvas is out of scope. Classification of `text-indent` and `transform` shifts (main `OFFSCREEN` vs `ETC`) is my reading of the contest definition.

### Possible extension

A model-based classifier could sit behind the dictionary stage to judge borderline text. It is intentionally not part of this version, which keeps the tool free of external services.