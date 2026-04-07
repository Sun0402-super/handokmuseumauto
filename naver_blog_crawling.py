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
        
        # [수정] Headless 모드일 때만 브라우저 창을 최소화합니다.
        if headless:
            driver.minimize_window()
        wait = WebDriverWait(driver, 15)

        # 1. 네이버 검색 직접 접속 (최신순, 1주일 필터 작동)
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={query}&sm=tab_opt&nso=so%3Add%2Cp%3A1w"
        driver.get(url)
        time.sleep(3) # 로딩 대기 시간 증가
        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        # 2. 결과 추출 (선택자 보강)
        results_count = 0
        
        for page in range(1, max_pages + 1):
            yield f"[{page}페이지] 검색 결과 추출 중..."
            
            # [최신 보강] 네이버의 최신 동적 레이아웃(Fender) 및 기존 VIEW 모두 대응 
            posts_selectors = [
                "div.api_subject_bx", # 최신 표준 컨테이너
                "div.GgwGYVzOUr_7Xzt0T0mI", 
                "div.X91NYa7h9SUdFslwWPfv", 
                "li.bx", 
                "div.view_wrap",
                "li[role='listitem']"
            ]
            posts_elems = []
            for selector in posts_selectors:
                posts_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                if len(posts_elems) >= 3: 
                    yield f"✅ {len(posts_elems)}필터링 전 검색 결과 발견 ({selector})"
                    break 
            
            if not posts_elems:
                yield "⚠️ 검색 결과 목록을 인식하지 못했습니다. 레이아웃이 변경되었을 수 있습니다."
                continue
            
            for i, p in enumerate(posts_elems, 1):
                try:
                    # 1. 제목 및 URL (가장 중요한 정보)
                    title_elem = None
                    title_selectors = ["a.T4d_tSMrB8qRjbb9_yER", "a.P_gXr2Vm5cF3ms_AxCoa", "a.xB7GMuBWFEZ36I3LWUaT", "a.title_link", "a.api_txt_lines"]
                    for selector in title_selectors:
                        try:
                            title_elem = p.find_element(By.CSS_SELECTOR, selector)
                            if title_elem: break
                        except: continue
                    
                    if not title_elem: continue
                    
                    # innerText를 사용하여 <mark> 등 하위 태그 텍스트를 유실 없이 합침
                    title = title_elem.get_attribute("innerText").strip()
                    link = title_elem.get_attribute("href")
                    
                    # 2. 작성자 정보 추출 보강
                    author = "익명"
                    author_selectors = ["a.fender-ui_475445f0", "span.sds-comps-profile-info-title-text", "a[class*='name']", "span.elps1"]
                    for selector in author_selectors:
                        try:
                            author_elem = p.find_element(By.CSS_SELECTOR, selector)
                            author = author_elem.get_attribute("innerText").strip()
                            if author: break
                        except: continue
                    
                    yield f"🔍 [{i}] {author}님의 글 분석 중..."
                    
                    # 3. 작성일 정보 추출 보강
                    date = "-"
                    date_selectors = ["span.sds-comps-profile-info-subtext", "span.sub_time", "span.txt_sub"]
                    for selector in date_selectors:
                        try:
                            date_elem = p.find_element(By.CSS_SELECTOR, selector)
                            date = date_elem.get_attribute("innerText").strip()
                            if date: break
                        except: continue
                    
                    # 4. 본문 내용 스니펫 추출 보강
                    content_snippet = ""
                    snippet_selectors = ["a.fds-ugc-ellipsis2", "a.fds-ugc-ellipsis3", "span.sds-comps-text-type-body1", "div.api_txt_lines", "p.dsc_txt"]
                    for selector in snippet_selectors:
                        try:
                            content_snippet = p.find_element(By.CSS_SELECTOR, selector).get_attribute("innerText").strip()
                            if content_snippet: break
                        except: continue

                    # 감성 분석 (스니펫 기준)
                    sentiment, reason = "", ""
                    if use_sentiment and content_snippet:
                        sentiment, reason = analyze_sentiment(content_snippet, api_key, use_summary=use_summary)

                    yield {
                        "출처": "네이버 블로그",
                        "작성자": author,
                        "제목": title,
                        "작성일": parse_date_to_string(date),
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
