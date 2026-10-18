"""result.json 의 각 finding 위치(location)가 실제 페이지에서 정확히 1개 요소만 가리키는지 검증한다.
(채점: 선택자가 2개 이상 요소에 맞으면 오답)  사용:  python verify_selectors.py [result.json]
iframe 안의 요소는 'iframe[src="..."] >>> 선택자' 형태로 기록되어 있으므로 프레임을 따라 들어가서 센다."""
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path


async def count_matches(page, location: str) -> int:
    """모집요강 규칙대로 해석한다: iframe[src="절대주소"] >>> 선택자 (src 는 상대경로를 절대주소로 푼 값과 비교)."""
    import re
    parts = [p.strip() for p in location.split(" >>> ")]
    frame = page.main_frame
    for frame_sel in parts[:-1]:
        m = re.fullmatch(r'iframe\[src="(.*)"\]', frame_sel)
        if not m:
            return -1
        target = m.group(1)
        hits = []
        for h in await frame.query_selector_all("iframe"):
            if await h.evaluate("(el) => el.src") == target:      # el.src 는 브라우저가 절대주소로 풀어 준 값
                hits.append(h)
        if len(hits) != 1:
            return len(hits)                                      # 0개 또는 같은 src 의 iframe 이 여러 개 -> 특정 불가
        frame = await hits[0].content_frame()
        if frame is None:
            return 0
    return len(await frame.query_selector_all(parts[-1]))


async def verify(result_path: Path) -> int:
    from playwright.async_api import async_playwright
    findings = json.load(open(result_path, encoding="utf-8-sig"))["findings"]
    by_url = defaultdict(list)
    for f in findings:
        by_url[f["url"]].append(f)
    bad = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="ko-KR")
        for url, items in by_url.items():
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="commit", timeout=45000)
                await page.wait_for_load_state("domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1500)
            except Exception as e:
                print(f"[접속 실패] {url}: {str(e).splitlines()[0]}")
                bad += len(items)
                await page.close()
                continue
            for f in items:
                n = -1
                for attempt in range(4):              # 페이지가 스스로 이동/갱신 중이면 잠잠해질 때까지 기다렸다가 다시 센다
                    try:
                        n = await count_matches(page, f["location"])
                        break
                    except Exception as e:
                        msg = str(e).splitlines()[0]
                        if attempt == 3:
                            print(f"[오류] {f['id']}: {msg}")
                        else:
                            try:
                                await page.wait_for_load_state("load", timeout=15000)
                            except Exception:
                                pass
                            await page.wait_for_timeout(2000)
                if page.url.rstrip("/") != url.rstrip("/"):
                    print(f"     (참고) 페이지가 이동함: {url} -> {page.url}")
                ok = (n == 1)
                bad += (not ok)
                print(f"{'OK ' if ok else 'BAD'} {f['id']} {f['technique']:<11} 일치 {n}개  {f['location'][:90]}")
            await page.close()
        await browser.close()
    print(f"\n총 {len(findings)}건 중 문제 {bad}건")
    return 1 if bad else 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("result.json")
    sys.exit(asyncio.run(verify(path)))