import asyncio, sys
from playwright.async_api import async_playwright

URL = sys.argv[1]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        print("최종 주소:", page.url)
        print("표 개수:", await page.locator("table").count())
        rows = await page.eval_on_selector_all(
            "tbody a, td a, .board_list a, .bbs a",
            "els => els.slice(0, 15).map(e => [e.getAttribute('href'), e.getAttribute('onclick'), (e.innerText||'').trim().slice(0,30)])")
        print("표 안 링크 수(최대 15개):", len(rows))
        for href, onclick, text in rows:
            print(f"href={href!r}  onclick={onclick!r}  text={text}")
        await b.close()

asyncio.run(main())