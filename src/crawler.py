#Web crawler, DOM parsing

import asyncio
import math
import re
import time
from collections import deque
from urllib.parse import urlparse, urljoin, parse_qsl, urlencode
from typing import List, Dict, Any, Set, Optional, Tuple
from playwright.async_api import async_playwright, Page, Frame

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
    """같은 생김새의 URL 이 방문 순서를 독점하지 못하게 하는 큐.
    각 '생김새'(템플릿)마다 점수 = (방문한 수 + 1) / sqrt(지금까지 발견된 수) 를 계산하고,
    점수가 가장 낮은 템플릿의 다음 URL 을 꺼낸다 (동률이면 먼저 발견된 템플릿).
     - 한 템플릿이 독점하지 못한다 (방문할수록 점수가 올라간다)
     - 대신 같은 모양이 많이 쏟아지는 템플릿(게시글 상세 등)은 몫이 조금 더 크다 (sqrt)
     - 시간이 충분하면 결국 전부 방문한다. 시간이 모자랄 때 다양한 유형을 먼저 본다."""
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


class WebCrawler:
    """
    공공 웹사이트 크롤링 및 DOM/CSS 정보 수집 모듈
    (스킴 분리, 중복 방지 키 적용, 고유 선택자, DOM src 기반 중첩 iframe 체인 지원)
    """
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
        """여러 탭(workers)이 같은 큐에서 동시에 페이지를 가져간다. 결과는 방문 순서대로 정렬해 돌려준다."""
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
            context = await browser.new_context()

            # 이미지/영상/폰트는 텍스트 탐지에 필요 없으므로 받지 않는다 (속도)
            async def _block_heavy(route):
                if route.request.resource_type in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", _block_heavy)

            async def worker(wid: int):
                page = await context.new_page()
                try:
                    while True:
                        if self.should_stop():
                            print("[!] 사용자 요청으로 크롤링을 중지합니다.")
                            return
                        if time.time() - start_time > self.total_timeout_sec:
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
                            print(f"[!] 페이지 처리 실패 ({target_url}): {type(e).__name__}: {e}")
                        finally:
                            state["busy"] -= 1
                            in_progress.discard(dedup_key)
                finally:
                    await page.close()

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
        try:
            response = await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print(f"[!] 페이지 접속 실패 ({target_url}): {e}")
            return
        t1 = time.time()
        # 동적으로 붙는 내용(댓글 등)을 위해 네트워크가 잠잠해질 때까지 최대 2초, 그 뒤 잠깐 더
        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        timing["goto"] += time.time() - t0

        if response is not None and response.status >= 400:
            print(f"[!] HTTP {response.status}: {target_url}")
            return
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
        """
        중첩 iframe 상위 체인 추적:
        리다이렉트 전 DOM 태그의 원본 src 속성값을 직접 읽어오도록 개선
        """
        chain = []
        curr_frame: Optional[Frame] = frame
        
        while curr_frame and curr_frame.parent_frame:
            parent = curr_frame.parent_frame
            raw_src = ""
            
            try:
                # 부모 프레임에서 해당 iframe 요소의 DOM src 속성값 추출
                frame_element = await curr_frame.frame_element()
                raw_src = await frame_element.get_attribute("src") or ""
                
                # 상대 경로인 경우 부모 페이지 URL 기준 절대 경로로 조립
                if raw_src and not raw_src.startswith(('http://', 'https://', '//')):
                    raw_src = urljoin(parent.url, raw_src)
                elif raw_src.startswith('//'):
                    parsed_parent = urlparse(parent.url)
                    raw_src = f"{parsed_parent.scheme}:{raw_src}"
            except Exception:
                # DOM 접근 실패 시 fallback으로 frame.url 사용
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
                
                if parsed.netloc == self.domain and parsed.scheme in ('http', 'https'):
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

            function getUniqueCssSelector(el) {
                if (!(el instanceof Element)) return '';
                let path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    const parent = el.parentElement;

                    if (el.className && typeof el.className === 'string' && el.className.trim()) {
                        const validClasses = el.className.trim().split(/\\s+/).map(c => CSS.escape(c)).join('.');
                        selector += '.' + validClasses;
                    }

                    if (parent) {
                        const siblings = Array.from(parent.children);
                        const sameTagAndClassSiblings = siblings.filter(child => {
                            if (child.nodeName.toLowerCase() !== el.nodeName.toLowerCase()) return false;
                            return child.className === el.className;
                        });

                        if (sameTagAndClassSiblings.length > 1) {
                            let nth = 1;
                            let sibling = el;
                            while (sibling = sibling.previousElementSibling) {
                                if (sibling.nodeName.toLowerCase() === el.nodeName.toLowerCase()) nth++;
                            }
                            selector += `:nth-of-type(${nth})`;
                        }
                    }

                    path.unshift(selector);
                    el = el.parentElement;
                }
                return path.join(' > ');
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
            normalized_path = parsed.path.rstrip('/') if parsed.path != '/' else '/'
            
            query_str = ""
            if parsed.query:
                sorted_params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
                query_str = f"?{urlencode(sorted_params)}"

            return f"{scheme}://{parsed.netloc}{normalized_path}{query_str}"
        except Exception:
            return url

if __name__ == "__main__":
    async def test_run():
        crawler = WebCrawler("example.com", max_pages=10)
        result = await crawler.fetch_page_data()
        print(f"수집된 총 요소 수: {len(result['elements'])}")

    asyncio.run(test_run())
# 중복 수집: div, span 같은 래퍼 요소도 선택 대상입니다. 직접 텍스트가 없으면 text에 하위 전체 텍스트(fullInnerText)가 들어가므로, 같은 텍스트가 부모 요소 수만큼 반복해서 저장됩니다. 데이터가 불필요하게 커질 수 있습니다.
# 실패한 페이지도 카운트: visited_keys.add가 접속 시도 전에 실행되어서, 접속에 실패한 URL도 max_pages 카운트에 포함됩니다.
# response 변수는 안 쓰입니다. goto의 반환값을 받아놓고 사용하지 않습니다. HTTP 상태코드 확인에 쓸 수 있습니다.
# 고정 대기 1.5초: 느린 사이트에서는 렌더링이 안 끝나고, 빠른 사이트에서는 낭비입니다. 보통 특정 요소를 기다리는 wait_for_selector 등을 씁니다.
# pop(0)은 리스트 맨 앞 삭제라 O(n)입니다. 이 규모에선 문제없지만 큐에는 collections.deque가 정석입니다.
# 도메인 비교가 단순합니다. www.mois.go.kr과 mois.go.kr은 다른 도메인으로 취급됩니다.
# except Exception: return []는 에러를 조용히 삼킵니다. iframe 수집이 실패해도 알 수 없어서 디버깅이 어렵습니다.
# 리다이렉트에 약합니다. 중복 판별이 "요청한 URL" 기준이라, 서로 다른 URL이 같은 페이지로 리다이렉트되면 중복 방문됩니다.
# robots.txt를 확인하지 않고 요청 간 딜레이도 거의 없습니다. 공공 사이트에 돌릴 때는 서버 부하와 이용약관 면에서 확인이 필요합니다.