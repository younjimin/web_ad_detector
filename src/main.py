"""사용:  python main.py <URL> [--out result.json] [--max-pages 30] [--timeout 1200]
URL 을 생략하면 입력창으로 물어본다 (exe 더블클릭용)."""
import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from pipeline import run_all_detectors
from result_writer import DEFAULT_TOPIC, build_result, validate_result, write_result


def base_dir() -> Path:
    """exe 로 묶였으면 exe 가 있는 폴더, 아니면 이 스크립트 폴더."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


async def scan(entry_url: str, max_pages: int, timeout: float, workers: int):
    from crawler import WebCrawler          # playwright 는 여기서만 필요
    crawler = WebCrawler(entry_url, max_pages=max_pages, total_timeout_sec=timeout, workers=workers)
    return await crawler.fetch_page_data()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="공공 웹사이트 불법광고 탐지 도구")
    ap.add_argument("url", nargs="?", help="탐지 시작 URL")
    ap.add_argument("--out", default=None, help="결과 파일 경로 (기본: 실행 파일 옆 result.json)")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--timeout", type=float, default=1200.0, help="전체 크롤링 제한(초)")
    ap.add_argument("--workers", type=int, default=4, help="동시에 여는 탭 수")
    ap.add_argument("--topic", default=DEFAULT_TOPIC)
    args = ap.parse_args(argv)

    url = args.url or input("탐지할 URL 을 입력하세요: ").strip()
    if not url.lower().startswith(("http://", "https://")):
        print("[!] URL 은 http:// 또는 https:// 로 시작해야 합니다.")
        return 2
    out = Path(args.out) if args.out else base_dir() / "result.json"

    started = datetime.now().astimezone()
    findings, status = [], 0
    try:
        data = asyncio.run(scan(url, args.max_pages, args.timeout, args.workers))
        elements = data["elements"]
        print(f"[+] {data['visited_pages_count']}개 페이지, {len(elements)}개 요소 수집")
        findings = run_all_detectors(elements)
    except Exception as e:                    # 크롤링이 죽어도 빈 결과 파일은 남긴다
        print(f"[!] 실행 중 오류: {type(e).__name__}: {e}")
        status = 1
    finished = datetime.now().astimezone()

    result = build_result(url, started, finished, findings, args.topic)
    problems = validate_result(result)
    for p in problems:
        print("[!] 스키마 경고:", p)
    write_result(result, out)

    by_tech = {}
    for f in result["findings"]:
        by_tech[f["technique"]] = by_tech.get(f["technique"], 0) + 1
    print(f"[+] 탐지 {len(result['findings'])}건 {by_tech}  (소요 {result['meta']['elapsed_sec']}초)")
    print(f"[+] 결과 저장: {out.resolve()}")
    return status or (1 if problems else 0)


if __name__ == "__main__":
    sys.exit(main())