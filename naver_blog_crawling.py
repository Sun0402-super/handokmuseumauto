import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from filter_utils import is_relevant_by_keywords, is_within_one_week, parse_date_to_string
from driver_utils import setup_chrome_driver, capture_screenshot
from sentiment_utils import analyze_sentiment


# ============================================================
# 공통 유틸 함수
# ============================================================
def create_directory(dir_name):
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

def get_blog_content(driver, blog_url):
    """블로그 본문 내용을 Selenium 드라이버로 수집 (iframe 대응)"""
    try:
        driver.get(blog_url)
        time.sleep(1.5)
        
        # iframe으로 전환
        try:
            wait = WebDriverWait(driver, 7)
            iframe = wait.until(EC.presence_of_element_located((By.ID, "mainFrame")))
            driver.switch_to.frame(iframe)
            
            # 본문 추출
            content_div = driver.find_element(By.CSS_SELECTOR, 'div.se-main-container, #postViewArea')
            content = content_div.text.strip()
            
            # 다시 기본 컨텐츠로 복구
            driver.switch_to.default_content()
            return content
        except:
            return ""
    except:
        return ""

# ============================================================
# 메인 크롤링 함수 (Edge 브라우저 사용 제너레이터)
# ============================================================
def crawl_naver_blog(query, max_pages=1, api_key=None, use_sentiment=False, use_summary=True, headless=True):
    """
    네이버 블로그 검색결과를 Chrome 브라우저로 크롤링하는 제너레이터입니다.
    """
    driver = None
    try:
        yield "Chrome 브라우저를 시작합니다..."
        driver, status = setup_chrome_driver(headless=headless)
        if not driver:
            yield "❌ 크롬 브라우저를 시작할 수 없습니다."
            return
        
        # [수정] Headless 모드 시 창 조작은 생략합니다. (브라우저 충돌 방지)
        # if headless:
        #     driver.minimize_window()
        wait = WebDriverWait(driver, 15)

        # 1. 네이버 검색 직접 접속 (사용자가 제공한 URL 형식 사용)
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={query}&sm=tab_opt&nso=so%3Add%2Cp%3A1w"
        driver.get(url)
        time.sleep(5) # 레이아웃 안정화를 위해 대기 시간 증가
        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        # 2. 결과 추출 (선택자 보강)
        results_count = 0
        seen_urls = set()  # URL 기반 중복 방지
        
        for page in range(1, max_pages + 1):
            yield f"[{page}페이지] 검색 결과 추출 중..."
            
            # 가장 세밀한 개별 글 단위 선택자를 우선 탐색하여 중복 파싱 방지
            # data-template-id="ugcItem" : Fender 레이아웃에서 개별 글 단위로 정확하게 파싱
            # div.api_subject_bx 는 광고+글 묶음 컨테이너라 내부에 여러 글이 포함돼 중복 발생
            posts_selectors = [
                "[data-template-id='ugcItem']", # Fender 레이아웃 개별 글 단위 (최우선)
                "li.bx",                         # 기존 레이아웃
                "div.view_wrap",                 # 개별 글 단위
                "div.api_subject_bx"             # 최신 Fender (대안)
            ]
            posts_elems = []
            for selector in posts_selectors:
                posts_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                if len(posts_elems) >= 1:
                    yield f"✅ {len(posts_elems)}건의 검색 결과 발견 ({selector})"
                    break
            
            if not posts_elems:
                yield "⚠️ 검색 결과 목록을 인식하지 못했습니다. 레이아웃이 변경되었을 수 있습니다."
                continue
            
            for i, p in enumerate(posts_elems, 1):
                try:
                    # 1. 제목 및 URL — 클래스명이 난독화되어 있으므로 구조 기반으로 탐색
                    title_elem = None
                    title = ""
                    link = ""

                    # 1-a. 고정 클래스명 셀렉터 (먼저 시도)
                    title_selectors_fixed = [
                        "a.title_link",           # 기존 레이아웃
                        "a.api_txt_lines",        # 기존 레이아웃 (본문)
                    ]
                    for selector in title_selectors_fixed:
                        try:
                            title_elem = p.find_element(By.CSS_SELECTOR, selector)
                            if title_elem:
                                break
                        except:
                            continue

                    # 1-b. 구조 기반 탐색: naver.com 도메인 링크 중 가장 텍스트가 긴 것을 제목으로
                    if not title_elem:
                        try:
                            candidates = p.find_elements(By.CSS_SELECTOR, "a[href]")
                            best = None
                            best_len = 0
                            for a in candidates:
                                href = a.get_attribute("href") or ""
                                # 블로그/포스트 링크만 대상으로 함
                                if "blog.naver.com" in href or "m.blog.naver.com" in href:
                                    text = (a.get_attribute("innerText") or "").strip()
                                    if len(text) > best_len:
                                        best_len = len(text)
                                        best = a
                            if best and best_len > 0:
                                title_elem = best
                        except:
                            pass

                    if not title_elem:
                        continue

                    # innerText를 사용하여 <mark> 등 하위 태그 텍스트를 유실 없이 합침
                    title = (title_elem.get_attribute("innerText") or "").strip()
                    link = title_elem.get_attribute("href") or ""

                    if not title:
                        continue

                    # URL 중복 체크 (같은 글이 2번 파싱되는 경우 방지)
                    if link and link in seen_urls:
                        yield f"   ⏩ [중복 제외] '{title[:20]}...'"
                        continue
                    if link:
                        seen_urls.add(link)
                    
                    # 2. 작성자 정보 추출
                    author = "익명"
                    author_selectors = [
                        "span.sds-comps-profile-info-title-text", # Fender 작성자 (가장 정확)
                        "a.sub_txt.sub_name",                     # 기존 작성자
                        "span.elps1"
                    ]
                    for selector in author_selectors:
                        try:
                            author_elem = p.find_element(By.CSS_SELECTOR, selector)
                            txt = (author_elem.get_attribute("innerText") or "").strip()
                            if txt:
                                author = txt
                                break
                        except:
                            continue

                    yield f"🔍 [{i}] {author}님의 글 분석 중..."
                    
                    # 3. 작성일 정보 추출 (사용자 제공 HTML 기반)
                    date_raw = "-"
                    # sds-comps-profile-info-subtext 는 같은 블록 내 여러 요소가 있을 수 있음
                    # find_elements로 전부 가져온 뒤 숫자/상대날짜 패턴인 것만 사용
                    date_selectors_multi = [
                        "span.sds-comps-profile-info-subtext", # Fender 날짜 (예: 2일 전)
                        "span.sub_time",                       # 기존 날짜
                        "span.txt_sub"
                    ]
                    _date_pattern = re.compile(r"(\d+\s*(일|주|달|개월|년)?\s*전|\d{4}[.\-]\d{1,2}[.\-]\d{1,2}|ago|hour|minute|second|just now)", re.IGNORECASE)
                    for selector in date_selectors_multi:
                        try:
                            date_elems = p.find_elements(By.CSS_SELECTOR, selector)
                            for de in date_elems:
                                candidate = de.get_attribute("innerText").strip()
                                if candidate and _date_pattern.search(candidate):
                                    date_raw = candidate
                                    break
                            if date_raw != "-": break
                        except: continue
                    # 여전히 못 찾았으면 첫 번째 요소라도 사용
                    if date_raw == "-":
                        for selector in date_selectors_multi:
                            try:
                                date_elem = p.find_element(By.CSS_SELECTOR, selector)
                                date_raw = date_elem.get_attribute("innerText").strip()
                                if date_raw: break
                            except: continue
                    
                    # 4. 본문 요약 내용 추출
                    content_snippet = ""
                    snippet_selectors = [
                        "a.fds-ugc-ellipsis2",           # Fender 2줄 요약
                        "a.fds-ugc-ellipsis3",           # Fender 3줄 요약
                        "span.sds-comps-text-type-body1", # Fender 요약 텍스트
                        "div.api_txt_lines.dsc_txt",     # 기존 요약
                        "p.dsc_txt"
                    ]
                    for selector in snippet_selectors:
                        try:
                            snippet_text = p.find_element(By.CSS_SELECTOR, selector).get_attribute("innerText") or ""
                            content_snippet = snippet_text.strip()
                            if content_snippet:
                                break
                        except:
                            continue

                    # [필터] 날짜를 찾지 못한 경우(date_raw=="-") → 7일 이내로 간주하고 포함
                    # [필터] 날짜를 찾은 경우 → 7일 초과 시 제외
                    if date_raw != "-" and not is_within_one_week(date_raw):
                        yield f"   ⏩ [날짜 제외] '{title[:20]}...' ({date_raw})"
                        continue

                    # 감성 분석 (스니펫 기준)
                    sentiment, reason = "", ""
                    if use_sentiment and content_snippet:
                        sentiment, reason = analyze_sentiment(content_snippet, api_key, use_summary=use_summary)

                    # 사용자 요청에 맞춘 결과 딕셔너리 구성
                    yield {
                        "출처": "네이버 블로그",
                        "작성자": author,
                        "제목": title,
                        "작성일": parse_date_to_string(date_raw),
                        "URL": link,
                        "본문내용": content_snippet,
                        "감성분석": sentiment,
                        "분석이유": reason
                    }
                    results_count += 1
                    
                except Exception as e:
                    continue
            
            # 다음 페이지 스크롤 (또는 종료)
            if page < max_pages:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                yield {"type": "screenshot", "data": capture_screenshot(driver)}
            else:
                break

        yield f"네이버 블로그 수집 완료 (총 {results_count}건)"

    except Exception as e:
        yield f"네이버 수집 중 오류: {e}"
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    for item in crawl_naver_blog("한독의약박물관", max_pages=1):
        print(item)
