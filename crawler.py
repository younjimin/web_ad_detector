#Web crawler, DOM parsing

import asyncio
import time
from urllib.parse import urlparse, urljoin, parse_qsl, urlencode
from typing import List, Dict, Any, Set, Optional, Tuple
from playwright.async_api import async_playwright, Page, Frame

class WebCrawler:
    """
    공공 웹사이트 크롤링 및 DOM/CSS 정보 수집 모듈
    (스킴 분리, 중복 방지 키 적용, 고유 선택자, DOM src 기반 중첩 iframe 체인 지원)
    """
    def __init__(self, entry_url: str, max_pages: int = 30, total_timeout_sec: float = 1200.0):
        self.entry_url = entry_url.strip()
        self.parsed_entry = urlparse(self.entry_url)
        self.domain = self.parsed_entry.netloc
        self.max_pages = max_pages            
        self.total_timeout_sec = total_timeout_sec  
        self.visited_keys: Set[str] = set()

    async def fetch_page_data(self) -> Dict[str, Any]:
        print(f"[*] 웹 크롤링 시작 (진입점: {self.entry_url}, 도메인: {self.domain})")
        start_time = time.time()
        
        all_elements_data: List[Dict[str, Any]] = []
        
        entry_normalized = self._normalize_url(self.entry_url)
        entry_key = self._get_dedup_key(entry_normalized)
        
        urls_to_visit: List[Tuple[str, str]] = [(entry_normalized, entry_key)]
        queued_keys: Set[str] = {entry_key}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            while urls_to_visit and len(self.visited_keys) < self.max_pages:
                elapsed_time = time.time() - start_time
                if elapsed_time > self.total_timeout_sec:
                    print(f"[!] 타임아웃 상한선({self.total_timeout_sec}초) 도달로 크롤링을 종료합니다.")
                    break

                target_url, dedup_key = urls_to_visit.pop(0)
                
                if dedup_key in self.visited_keys:
                    continue

                self.visited_keys.add(dedup_key)
                print(f"[{len(self.visited_keys)}/{self.max_pages}] 크롤링 중: {target_url}")

                try:
                    response = await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.5)
                except Exception as e:
                    print(f"[!] 페이지 접속 실패 ({target_url}): {e}")
                    continue

                # 1. 메인 프레임 및 모든 iframe 순회 수집
                for frame in page.frames:
                    is_iframe = (frame != page.main_frame)
                    iframe_chain = await self._build_iframe_chain(frame) if is_iframe else ""
                    
                    frame_elements = await self._extract_elements_from_frame(
                        frame, is_iframe=is_iframe, iframe_chain=iframe_chain, page_url=target_url
                    )
                    all_elements_data.extend(frame_elements)

                # 2. 동일 도메인 하위 링크 수집
                sub_links = await self._extract_same_domain_links(page)
                for link in sub_links:
                    norm_link = self._normalize_url(link)
                    link_key = self._get_dedup_key(norm_link)
                    
                    if norm_link and link_key not in self.visited_keys and link_key not in queued_keys:
                        queued_keys.add(link_key)
                        urls_to_visit.append((norm_link, link_key))

            await browser.close()
            total_elapsed = time.time() - start_time
            print(f"[+] 총 {len(self.visited_keys)}개 페이지 탐색, {len(all_elements_data)}개 요소 수집 완료")

            return {
                "entry_url": self.entry_url,
                "visited_pages_count": len(self.visited_keys),
                "crawl_elapsed_sec": total_elapsed,
                "elements": all_elements_data
            }

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
                const fullInnerText = (el.innerText || '').trim();
                
                if (trimmedDirectText.length > 0 || fullInnerText.length > 0) {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();

                    results.push({
                        text: trimmedDirectText || fullInnerText,
                        direct_text: trimmedDirectText,
                        full_text: fullInnerText,
                        location: getUniqueCssSelector(el),
                        style: {
                            opacity: style.opacity,
                            color: style.color,
                            backgroundColor: style.backgroundColor,
                            display: style.display,
                            visibility: style.visibility,
                            fontSize: style.fontSize,
                            position: style.position,
                            left: style.left,
                            top: style.top
                        },
                        rect: {
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            left: rect.left
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
        except Exception:
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