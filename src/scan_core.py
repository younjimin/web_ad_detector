"""탐지 실행의 공통 코드. 명령줄(main.py)과 화면(gui.py)이 같은 함수를 쓴다.
 크롤링 -> 탐지기 4종 -> result.json 작성 -> HTML 리포트 작성"""
import asyncio
import contextlib
import io
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

# exe 로 묶였을 때 Playwright 가 패키지 안에 같이 넣어 둔 Chromium 을 쓰도록 한다 (빌드 때 PLAYWRIGHT_BROWSERS_PATH=0 으로 설치)
if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

from pipeline import run_all_detectors
from report import write_report
from result_writer import DEFAULT_TOPIC, build_result, validate_result, write_result

DEFAULT_MAX_PAGES = 1000
DEFAULT_TIMEOUT_SEC = 1500.0      # 심사 시간 상한 30분보다 여유를 둔 크롤링 제한(25분)
DEFAULT_WORKERS = 4


def base_dir() -> Path:
    """exe 로 묶였으면 exe 가 있는 폴더, 아니면 이 스크립트 폴더. (결과 파일은 여기에 만든다)"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


async def _crawl(entry_url, max_pages, timeout, workers, should_stop):
    from crawler import WebCrawler          # playwright 는 여기서만 필요
    crawler = WebCrawler(entry_url, max_pages=max_pages, total_timeout_sec=timeout, workers=workers)
    if should_stop:
        crawler.should_stop = should_stop
    return await crawler.fetch_page_data()


def default_crawl(entry_url, max_pages, timeout, workers, should_stop):
    return asyncio.run(_crawl(entry_url, max_pages, timeout, workers, should_stop))


class _LineWriter(io.TextIOBase):
    """print() 로 나오는 크롤러 로그를 한 줄씩 log 함수로 넘긴다."""
    def __init__(self, log: Callable[[str], None]):
        self.log, self.buf = log, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.log(line)
        return len(s)

    def flush(self):
        pass


def run_scan(url: str, *, max_pages: int = DEFAULT_MAX_PAGES, timeout: float = DEFAULT_TIMEOUT_SEC,
             workers: int = DEFAULT_WORKERS, topic: str = DEFAULT_TOPIC, out_dir: Optional[Path] = None,
             log: Callable[[str], None] = print, should_stop: Optional[Callable[[], bool]] = None,
             crawl_fn: Optional[Callable] = None) -> Dict:
    """탐지를 끝까지 실행하고 파일을 만든다. 크롤링이 도중에 죽어도 빈 결과 파일은 남긴다."""
    out_dir = Path(out_dir) if out_dir else base_dir()
    real_out = sys.stdout                       # 리다이렉트 전의 진짜 stdout
    if log is print:                            # print 를 그대로 쓰면 리다이렉트된 stdout 으로 다시 들어가 무한 재귀가 된다
        log = lambda s: (real_out.write(s + "\n"), real_out.flush())
    started = datetime.now().astimezone()                   # '탐지 시작' 시각
    findings: List[Dict] = []
    pages, n_elements, status, error = 0, 0, 0, None
    stopped = False

    try:
        with contextlib.redirect_stdout(_LineWriter(log)):
            data = (crawl_fn or default_crawl)(url, max_pages, timeout, workers, should_stop)
        pages, n_elements = data["visited_pages_count"], len(data["elements"])
        log(f"[+] {pages}개 페이지, {n_elements}개 요소 수집")
        log("[*] 탐지기 실행 중...")
        with contextlib.redirect_stdout(_LineWriter(log)):
            findings = run_all_detectors(data["elements"])
    except Exception as e:                                   # 크롤링이 죽어도 빈 결과 파일은 남긴다
        error = f"{type(e).__name__}: {e}"
        log(f"[!] 실행 중 오류: {error}")
        status = 1
    stopped = bool(should_stop and should_stop())
    finished = datetime.now().astimezone()

    result = build_result(url, started, finished, findings, topic)
    problems = validate_result(result)
    for p in problems:
        log(f"[!] 스키마 경고: {p}")

    result_path = write_result(result, out_dir / "result.json")
    details = {(f["url"], f["location"], f["technique"]): f.get("detail", {}).get("reason", "") for f in findings}
    try:
        report_path = write_report(result, out_dir / "report.html", details)
    except Exception as e:
        log(f"[!] 리포트 생성 실패: {e}")
        report_path = None

    by_tech: Dict[str, int] = {}
    for f in result["findings"]:
        by_tech[f["technique"]] = by_tech.get(f["technique"], 0) + 1
    log(f"[+] 탐지 {len(result['findings'])}건 {by_tech} (소요 {result['meta']['elapsed_sec']}초)")
    log(f"[+] 결과 저장: {result_path.resolve()}")
    return {"result": result, "details": details, "result_path": result_path, "report_path": report_path,
            "pages": pages, "elements": n_elements, "problems": problems, "error": error,
            "stopped": stopped, "status": status or (1 if problems else 0)}