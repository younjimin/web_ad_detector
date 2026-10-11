# 공공 웹사이트 불법광고 자동 탐지 도구 (Public WebScan)

> **2026 행정안전부 · NIA 주최 「공공 웹사이트 불법광고 탐지 도구 개발 공모전」 제출용 자동화 프로그램**

## 🛠️ 프로젝트 구조 (Directory Structure)

📁 web_ad_detector
 ├── 📁 .github/workflows
 │    └── 📄 build.yml         # GitHub Actions x64 Windows 자동 빌드 CI/CD
 ├── 📁 detectors                   # 4대 탐지 알고리즘 전용 패키지
 │    ├── 📄 __init__.py
 │    ├── 📄 homoglyph.py           # HOMOGLYPH(닮은꼴 글자) 탐지 모듈
 │    ├── 📄 jamo.py                # JAMO(자모 분해) 탐지 모듈
 │    ├── 📄 transparent.py         # TRANSPARENT(투명 텍스트) 탐지 모듈
 │    └── 📄 offscreen.py           # OFFSCREEN(화면 밖 은닉) 탐지 모듈
 ├── 📄 crawler.py                  # Playwright 기반 동적 크롤러 및 DOM/CSS 파서
 ├── 📄 reporter.py                 # result.json 스키마 저장 모듈
 ├── 📄 main.py                     # 파이프라인 총괄 메인 실행 파일
 ├── 📄 requirements.txt            # 프로젝트 의존성 라이브러리 목록
 └── 📄 README.md                   # 프로젝트 안내 문서