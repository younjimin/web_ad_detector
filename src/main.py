"""실행:
   python main.py                  -> 화면(GUI) 실행
   python main.py <URL> [옵션]      -> 명령줄 실행 (화면 없이 result.json 만 생성)
옵션: --out 폴더  --max-pages N  --timeout 초  --workers N"""
import argparse
import sys

# 콘솔/리다이렉트 환경의 인코딩이 한글을 못 써도 출력 때문에 프로그램이 죽지 않게 한다
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

from scan_core import (DEFAULT_MAX_PAGES, DEFAULT_TIMEOUT_SEC, DEFAULT_WORKERS, DEFAULT_TOPIC, run_scan)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="공공 웹사이트 불법광고 탐지 도구")
    ap.add_argument("url", nargs="?", help="탐지 시작 URL (생략하면 화면이 열린다)")
    ap.add_argument("--out", default=None, help="결과 파일을 만들 폴더 (기본: 실행 파일이 있는 폴더)")
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC, help="크롤링 제한 시간(초)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="동시에 여는 탭 수")
    ap.add_argument("--topic", default=DEFAULT_TOPIC)
    args = ap.parse_args(argv)

    if not args.url:
        from gui import run_gui
        run_gui()
        return 0

    if not args.url.lower().startswith(("http://", "https://")):
        print("[!] URL 은 http:// 또는 https:// 로 시작해야 합니다.")
        return 2
    out = run_scan(args.url, max_pages=args.max_pages, timeout=args.timeout, workers=args.workers,
                   topic=args.topic, out_dir=args.out)
    return out["status"]


if __name__ == "__main__":
    sys.exit(main())