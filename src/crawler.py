"""진입 URL에서 시작해 같은 도메인의 페이지를 돌면서, 페이지마다 텍스트 요소와 스타일·위치(CSS 선택자)를 모은다."""

import asyncio
import math
import re
import time
from collections import deque
from urllib.parse import urlparse, urljoin, parse_qsl, urlencode
from typing import List, Dict, Any, Set, Optional, Tuple
from playwright.async_api import async_playwright, Page, Frame

# 이 확장자로 끝나는 주소는 페이지가 아니라 파일이라 따라가지 않는다
FILE_EXTS = (".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".7z",
             ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".mp3", ".mp4", ".avi", ".wmv", ".mov",
             ".txt", ".csv", ".xml", ".json", ".exe", ".apk", ".css", ".js", ".ico")


class PageCrashed(Exception):
    """브라우저 탭이 죽었을 때(메모리 부족 등) 던진다. 탭을 새로 열어야 한다."""


def url_template(url: str) -> str:
    """URL 의 '생김새'. 숫자를 #로 바꾸고 쿼리는 키 순서로 정렬한다.
    예) /bbs/view.do?nttId=123&bbsId=BBSMSTR_0004 -> /bbs/view.do?bbsId=BBSMSTR_#&nttId=#"""
    try:
        u = urlparse(url)
        path = re.sub(r"\d+", "#", u.path)
        pairs = sorted((k, re.sub(r"\d+", "#", v)) for k, v in parse_qsl(u.query, keep_blank_values=True))
        return path + ("?" + "&".join(f"{k}={v}" for k, v in pairs) if pairs else "")
    except Exception:
        return url


class FairQueue:
    """게시글 상세처럼 같은 모양의 URL 이 수천 개 쏟아져도 다른 유형의 페이지가 밀리지 않게 하는 큐.
    템플릿마다 점수 (방문한 수 + 1) / sqrt(발견된 수) 를 매기고, 점수가 가장 낮은 템플릿에서 다음 URL 을 꺼낸다.
    많이 발견된 템플릿일수록 몫이 조금 더 크지만, 방문할수록 점수가 올라가서 한 템플릿이 독점하지는 못한다.
    시간이 충분하면 전부 방문하고, 모자라면 다양한 유형을 먼저 보게 된다."""
    def __init__(self):
        self.buckets: Dict[str, deque] = {}
        self.taken: Dict[str, int] = {}
        self.seen: Dict[str, int] = {}

    def append(self, item: Tuple[str, str]) -> None:
        t = url_template(item[0])
        if t not in self.buckets:
            self.buckets[t] = deque()
            self.taken[t] = 0
            self.seen[t] = 0
        self.buckets[t].append(item)
        self.seen[t] += 1

    def popleft(self) -> Tuple[str, str]:
        best, best_score = None, None
        for t, q in self.buckets.items():
            if not q:
                continue
            score = (self.taken[t] + 1) / math.sqrt(self.seen[t])
            if best is None or score < best_score:
                best, best_score = t, score
        if best is None:
            raise IndexError("empty")
        self.taken[best] += 1
        return self.buckets[best].popleft()

    def __len__(self) -> int:
        return sum(len(q) for q in self.buckets.values())

async def _normal_user_agent(browser) -> str:
    """헤드리스 Chromium 의 UA 에는 'HeadlessChrome' 이 들어 있어 일부 사이트가 접속을 막는다. 일반 Chrome 표기로 맞춘다."""
    ua = browser.version
    return (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{ua} Safari/537.36")


class WebCrawler:
    """같은 도메인의 페이지를 여러 탭으로 돌면서 요소 정보를 모은다. iframe 안쪽 요소도 함께 수집한다."""
    def __init__(self, entry_url: str, max_pages: int = 30, total_timeout_sec: float = 1200.0, workers: int = 4):
        self.entry_url = entry_url.strip()
        self.parsed_entry = urlparse(self.entry_url)
        self.domain = self.parsed_entry.netloc
        self.max_pages = max_pages
        self.total_timeout_sec = total_timeout_sec
        self.workers = max(1, workers)
        self.should_stop = lambda: False      # GUI 의 '중지' 버튼용: True 를 돌려주면 새 페이지를 가져가지 않고 끝낸다
        self.visited_keys: Set[str] = set()

    async def fetch_page_data(self) -> Dict[str, Any]:
        """탭 여러 개가 한 큐에서 페이지를 가져가 동시에 처리한다. 결과는 방문 순서대로 정렬해 돌려준다."""
        print(f"[*] 웹 크롤링 시작 (진입점: {self.entry_url}, 도메인: {self.domain}, 동시 탭: {self.workers})")
        start_time = time.time()

        entry_normalized = self._normalize_url(self.entry_url)
        entry_key = self._get_dedup_key(entry_normalized)

        urls_to_visit = FairQueue()
        urls_to_visit.append((entry_normalized, entry_key))
        queued_keys: Set[str] = {entry_key}
        in_progress: Set[str] = set()
        page_results: List[Tuple[int, List[Dict[str, Any]]]] = []   # (방문 순번, 요소들)
        state = {"claimed": 0, "busy": 0}
        timing = {"goto": 0.0, "extract": 0.0, "links": 0.0}       # 탭별 시간의 합(누적)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ua = await _normal_user_agent(browser)
            context = await browser.new_context(user_agent=ua, locale="ko-KR")

            # 텍스트만 보면 되니 이미지·영상·폰트는 받지 않는다
            async def _block_heavy(route):
                if route.request.resource_type in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", _block_heavy)

            retried: Set[str] = set()                   # 탭이 죽어서 한 번 다시 시도한 주소
            RECYCLE_EVERY = 40                          # 탭 하나가 이만큼 처리하면 새 탭으로 바꿔 메모리 누적을 막는다

            async def worker(wid: int):
                page = await context.new_page()
                done_here = 0
                try:
                    while True:
                        if self.should_stop():
                            print("[!] 사용자 요청으로 크롤링을 중지합니다.")
                            return
                        if time.time() - start_time > self.total_timeout_sec:
                            if not state.get("timeout_msg"):
                                state["timeout_msg"] = True
                                print(f"[!] 제한 시간({self.total_timeout_sec:.0f}초)에 도달해 크롤링을 마칩니다.")
                            return
                        if len(self.visited_keys) + state["busy"] >= self.max_pages:
                            return
                        try:
                            target_url, dedup_key = urls_to_visit.popleft()
                        except IndexError:
                            if state["busy"] == 0:
                                return                      # 큐도 비었고 일하는 탭도 없음 -> 끝
                            await asyncio.sleep(0.1)        # 다른 탭이 새 링크를 넣을 수 있으니 잠깐 대기
                            continue
                        if dedup_key in self.visited_keys or dedup_key in in_progress:
                            continue

                        in_progress.add(dedup_key)
                        state["busy"] += 1
                        state["claimed"] += 1
                        order = state["claimed"]
                        print(f"[{order}/{self.max_pages}] 크롤링 중: {target_url}")
                        try:
                            await self._crawl_one(page, target_url, dedup_key, order, page_results,
                                                  urls_to_visit, queued_keys, timing)
                        except Exception as e:
                            crashed = isinstance(e, PageCrashed) or "crash" in str(e).lower() or page.is_closed()
                            if crashed:
                                print(f"[!] 탭이 종료되어 새 탭으로 교체합니다 ({target_url})")
                                if dedup_key not in retried:        # 새 탭에서 한 번만 다시 시도
                                    retried.add(dedup_key)
                                    urls_to_visit.append((target_url, dedup_key))
                                try:
                                    await page.close()
                                except Exception:
                                    pass
                                page = await context.new_page()
                                done_here = 0
                            else:
                                print(f"[!] 페이지 처리 실패 ({target_url}): {type(e).__name__}: {e}")
                        finally:
                            state["busy"] -= 1
                            in_progress.discard(dedup_key)
                        done_here += 1
                        if done_here >= RECYCLE_EVERY:
                            try:
                                await page.close()
                            except Exception:
                                pass
                            page = await context.new_page()
                            done_here = 0
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

            await asyncio.gather(*(worker(i) for i in range(self.workers)))
            await browser.close()

        total_elapsed = time.time() - start_time
        page_results.sort(key=lambda t: t[0])
        all_elements_data = [e for _, els in page_results for e in els]
        print(f"[+] 총 {len(self.visited_keys)}개 페이지 탐색, {len(all_elements_data)}개 요소 수집 완료")
        print(f"[시간] (탭 누적) 접속+대기 {timing['goto']:.1f}초 / 요소 추출 {timing['extract']:.1f}초 / "
              f"링크 수집 {timing['links']:.1f}초 | 실제 경과 {total_elapsed:.1f}초")
        return {
            "entry_url": self.entry_url,
            "visited_pages_count": len(self.visited_keys),
            "crawl_elapsed_sec": total_elapsed,
            "elements": all_elements_data,
        }

    async def _crawl_one(self, page: Page, target_url: str, dedup_key: str, order: int,
                         page_results, urls_to_visit, queued_keys, timing) -> None:
        t0 = time.time()
        response = None
        for attempt, limit in enumerate((30000, 45000)):
            try:
                # 서버가 응답을 시작하면(commit) 일단 진행하고, 본문은 아래에서 따로 기다린다
                response = await page.goto(target_url, wait_until="commit", timeout=limit)
                break
            except Exception as e:
                msg = str(e).splitlines()[0]
                if "Download is starting" in msg:           # 파일 다운로드 주소: 페이지가 아니므로 조용히 건너뜀
                    return
                if "crash" in msg.lower() or page.is_closed():
                    raise PageCrashed(msg)
                if attempt == 0:
                    print(f"[!] 접속 지연, 재시도합니다 ({target_url}): {msg}")
                else:
                    print(f"[!] 페이지 접속 실패 ({target_url}): {msg}")
                    return
        # 본문 텍스트가 생길 때까지 최대 10초 기다린다 (DOMContentLoaded 는 외부 스크립트 때문에 늦기도 해서 본문 기준으로 본다)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=25000)
        except Exception:
            pass
        ready = False
        for _ in range(20):
            try:
                ready = await page.evaluate("() => !!(document.body && document.body.innerText && document.body.innerText.trim().length > 0)")
            except Exception:
                ready = False
            if ready:
                break
            await asyncio.sleep(0.5)
        if not ready:
            print(f"[!] 본문이 비어 있어 건너뜁니다 ({target_url})")
            return
        # iframe 안의 문서도 로드될 때까지 기다린다. iframe 안에 iframe 이 있을 수 있어 프레임 수가 안 늘 때까지(최대 3번) 반복
        for _ in range(3):
            n_before = len(page.frames)
            for fr in list(page.frames):
                if fr == page.main_frame:
                    continue
                try:
                    await fr.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
            await asyncio.sleep(0.2)
            if len(page.frames) == n_before:
                break
        # 댓글처럼 나중에 붙는 내용을 위해 네트워크가 잠잠해질 때까지 최대 2초 기다린다
        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        timing["goto"] += time.time() - t0

        if response is not None and response.status >= 400:
            print(f"[!] HTTP {response.status}: {target_url}")
            return
        final_key = self._get_dedup_key(page.url)
        if final_key != dedup_key:                      # 리다이렉트로 다른 주소에 도착
            if final_key in self.visited_keys:
                print(f"[-] 이미 방문한 페이지로 이동하여 건너뜁니다: {target_url} -> {page.url}")
                self.visited_keys.add(dedup_key)
                return
            self.visited_keys.add(final_key)
        self.visited_keys.add(dedup_key)

        t0 = time.time()
        elements: List[Dict[str, Any]] = []
        for frame in page.frames:
            is_iframe = (frame != page.main_frame)
            iframe_chain = await self._build_iframe_chain(frame) if is_iframe else ""
            elements.extend(await self._extract_elements_from_frame(
                frame, is_iframe=is_iframe, iframe_chain=iframe_chain, page_url=target_url))
        page_results.append((order, elements))
        timing["extract"] += time.time() - t0

        t0 = time.time()
        for link in await self._extract_same_domain_links(page):
            norm_link = self._normalize_url(link)
            link_key = self._get_dedup_key(norm_link)
            if norm_link and link_key not in self.visited_keys and link_key not in queued_keys:
                queued_keys.add(link_key)
                urls_to_visit.append((norm_link, link_key))
        timing["links"] += time.time() - t0

    async def _build_iframe_chain(self, frame: Frame) -> str:
        """바깥 iframe 부터 차례로 src 를 이어 붙인 위치 문자열을 만든다.
        리다이렉트되기 전 주소를 쓰려고 frame.url 대신 iframe 태그의 src 속성을 읽는다."""
        chain = []
        curr_frame: Optional[Frame] = frame

        while curr_frame and curr_frame.parent_frame:
            parent = curr_frame.parent_frame
            raw_src = ""

            try:
                frame_element = await curr_frame.frame_element()
                raw_src = await frame_element.get_attribute("src") or ""

                # 상대 경로는 부모 페이지 기준 절대 주소로 바꾼다
                if raw_src and not raw_src.startswith(('http://', 'https://', '//')):
                    raw_src = urljoin(parent.url, raw_src)
                elif raw_src.startswith('//'):
                    parsed_parent = urlparse(parent.url)
                    raw_src = f"{parsed_parent.scheme}:{raw_src}"
            except Exception:
                # 태그를 못 읽으면 frame.url 로 대신한다
                raw_src = curr_frame.url or "about:blank"

            chain.append(f'iframe[src="{raw_src}"]')
            curr_frame = parent

        chain.reverse()
        return " >>> ".join(chain)

    async def _extract_same_domain_links(self, page: Page) -> List[str]:
        try:
            hrefs = await page.eval_on_selector_all('a[href]', 'elements => elements.map(e => e.getAttribute("href"))')
            valid_links = []
            for href in hrefs:
                if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    continue

                full_url = urljoin(page.url, href)
                parsed = urlparse(full_url)

                if parsed.netloc == self.domain and parsed.scheme in ('http', 'https') \
                        and not parsed.path.lower().endswith(FILE_EXTS):
                    valid_links.append(full_url)
            return valid_links
        except Exception as e:
            print(f"[!] 하위 링크 추출 실패: {e}")
            return []

    async def _extract_elements_from_frame(self, frame: Frame, is_iframe: bool, iframe_chain: str, page_url: str) -> List[Dict[str, Any]]:
        frame_url = frame.url
        if not frame_url or frame_url == "about:blank":
            return []

        script = """
        () => {
            // 조상까지 올라가서 계산하는 '실제로 보이는' 값 (결과는 캐시)
            const opacityCache = new Map();
            const bgCache = new Map();

            function colorAlpha(c) {
                if (!c || c === 'transparent') return 0;
                const m = c.match(/rgba?\\(([^)]+)\\)/);
                if (!m) return 1;
                const p = m[1].split(',').map(s => s.trim());
                return p.length >= 4 ? parseFloat(p[3]) : 1;
            }

            // 조상 opacity 를 모두 곱한 값 (opacity 는 상속되지 않지만 자식도 같이 투명해진다)
            function effectiveOpacity(el) {
                if (!el || el.nodeType !== Node.ELEMENT_NODE) return 1;
                if (opacityCache.has(el)) return opacityCache.get(el);
                const own = parseFloat(window.getComputedStyle(el).opacity);
                const v = (isNaN(own) ? 1 : own) * effectiveOpacity(el.parentElement);
                opacityCache.set(el, v);
                return v;
            }

            // 자기 자신부터 올라가며 처음 만나는 '불투명한' 배경색. 없으면 페이지 기본색(흰색)
            function effectiveBackground(el) {
                if (!el || el.nodeType !== Node.ELEMENT_NODE) return 'rgb(255, 255, 255)';
                if (bgCache.has(el)) return bgCache.get(el);
                const bg = window.getComputedStyle(el).backgroundColor;
                const v = colorAlpha(bg) > 0.5 ? bg : effectiveBackground(el.parentElement);
                bgCache.set(el, v);
                return v;
            }

            // JS 가 수시로 바꾸는 상태/반응형 클래스는 선택자에 쓰지 않는다 (채점 시점에 값이 달라질 수 있음)
            const VOLATILE = new Set(['active','on','off','open','opened','close','closed','show','shown','hide','hidden-on',
                'selected','current','hover','focus','focused','loaded','loading','js','no-js','expanded','collapsed','checked',
                'disabled','sticky','fixed','scrolled','mobile','tablet','desktop','pc','slick-current','slick-active',
                'swiper-slide-active','swiper-slide-next','swiper-slide-prev']);
            function stableClasses(el) {
                if (!el.className || typeof el.className !== 'string') return '';
                return el.className.trim().split(/\\s+/).filter(c => c && !VOLATILE.has(c.toLowerCase())
                    && !/^(is|has)[-_]/i.test(c)).join(' ');
            }
            function buildSelector(el, useClasses) {
                let path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    const tag = el.nodeName.toLowerCase();
                    let selector = tag;
                    const parent = el.parentElement;
                    if (tag === 'html' || tag === 'body') {         // 문서에 하나뿐이라 클래스가 필요 없다
                        path.unshift(selector);
                        el = parent;
                        continue;
                    }
                    const mine = useClasses ? stableClasses(el) : '';
                    if (mine) selector += '.' + mine.split(' ').map(c => CSS.escape(c)).join('.');
                    if (parent) {
                        const same = Array.from(parent.children).filter(ch =>
                            ch.nodeName.toLowerCase() === tag && (!useClasses || stableClasses(ch) === mine));
                        if (same.length > 1) {
                            let nth = 1, sib = el;
                            while (sib = sib.previousElementSibling) {
                                if (sib.nodeName.toLowerCase() === tag) nth++;
                            }
                            selector += `:nth-of-type(${nth})`;
                        }
                    }
                    path.unshift(selector);
                    el = parent;
                }
                return path.join(' > ');
            }
            function isUnique(sel, el) {
                try {
                    const hits = el.ownerDocument.querySelectorAll(sel);
                    return hits.length === 1 && hits[0] === el;
                } catch (e) { return false; }
            }
            function getUniqueCssSelector(el) {
                if (!(el instanceof Element)) return '';
                const withClasses = buildSelector(el, true);
                if (isUnique(withClasses, el)) return withClasses;      // 사람이 읽기 쉬운 형태를 우선
                const structural = buildSelector(el, false);            // 클래스 없이 위치만으로
                return isUnique(structural, el) ? structural : withClasses;
            }

            const results = [];
            const elements = document.querySelectorAll('p, span, div, a, li, td, th, h1, h2, h3, h4, h5, h6, b, i, em, strong');

            elements.forEach(el => {
                let directText = '';
                for (let child of el.childNodes) {
                    if (child.nodeType === Node.TEXT_NODE) {
                        directText += child.textContent;
                    }
                }

                const trimmedDirectText = directText.trim();
                // 자기 글자가 없고 안쪽 글자가 300자를 넘는 큰 컨테이너는 건너뛴다.
                // (자식들이 따로 수집되므로 중복이고, innerText 계산이 느리다)
                if (!trimmedDirectText && (el.textContent || '').length > 300) return;
                const fullInnerText = (el.innerText || '').trim();

                if (trimmedDirectText.length > 0 || fullInnerText.length > 0) {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();

                    results.push({
                        text: trimmedDirectText || fullInnerText,
                        direct_text: trimmedDirectText,
                        full_text: fullInnerText,
                        location: getUniqueCssSelector(el),
                        eff_opacity: effectiveOpacity(el),
                        eff_bg: effectiveBackground(el),
                        style: {
                            opacity: style.opacity,

                            color: style.color,
                            backgroundColor: style.backgroundColor,

                            display: style.display,
                            visibility: style.visibility,

                            fontSize: style.fontSize,

                            position: style.position,

                            left: style.left,
                            top: style.top,

                            right: style.right,
                            bottom: style.bottom,

                            transform: style.transform,
                            textIndent: style.textIndent,

                            overflow: style.overflow,
                            clip: style.clip,
                            clipPath: style.clipPath,

                            zIndex: style.zIndex
                        },
                        rect: {
                            width: rect.width,
                            height: rect.height,

                            top: rect.top,
                            left: rect.left,

                            right: rect.right,
                            bottom: rect.bottom
                        }
                    });
                }
            });

            return results;
        }
        """

        try:
            extracted_data = await frame.evaluate(script)

            for item in extracted_data:
                item['url'] = page_url
                if is_iframe and iframe_chain:
                    item['location'] = f"{iframe_chain} >>> {item['location']}"


            return extracted_data
        except Exception as e:
            print(f"[!] 프레임 수집 실패 ({frame_url}): {e}")
            return []

    def _normalize_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            normalized_path = parsed.path.rstrip('/') if parsed.path != '/' else '/'
            query_str = f"?{parsed.query}" if parsed.query else ""
            return f"{parsed.scheme}://{parsed.netloc}{normalized_path}{query_str}"
        except Exception:
            return url

    def _get_dedup_key(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
            path = re.sub(r"/index\.(?:html?|php|jsp|asp|aspx|do)$", "/", parsed.path, flags=re.I)   # /index.html == /
            normalized_path = path.rstrip('/') if path != '/' else '/'

            query_str = ""
            if parsed.query:
                sorted_params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
                query_str = f"?{urlencode(sorted_params)}"

            return f"{scheme}://{parsed.netloc}{normalized_path}{query_str}"
        except Exception:
            return url