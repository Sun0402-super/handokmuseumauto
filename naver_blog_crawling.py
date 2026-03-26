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
def crawl_naver_blog(query, max_pages=1, api_key=None, use_sentiment=False, use_summary=True):
    """
    네이버 블로그 검색결과를 Chrome 브라우저로 크롤링하는 제너레이터입니다.
    """
    driver = None
    try:
        yield "Chrome 브라우저를 시작합니다..."
        driver, status = setup_chrome_driver(headless=True)
        if not driver:
            yield "❌ 크롬 브라우저를 시작할 수 없습니다."
            return
        # [수정] 사용자의 요청에 따라 브라우저 창을 최소화합니다.
        driver.minimize_window()
        wait = WebDriverWait(driver, 15)

        # 1. 네이버 검색 직접 접속 (ssc=tab.blog.all 및 필터 파라미터 포함)
        # nso=so:dd,p:1w (최신순, 1주일)
        url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={query}&sm=tab_opt&nso=so%3Add%2Cp%3A1w"
        driver.get(url)
        time.sleep(2)
        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        # 2. 결과 추출 (사용자가 제공한 HTML 구조에 맞춤)
        results_count = 0
        
        for page in range(1, max_pages + 1):
            yield f"[{page}페이지] 검색 결과 추출 중..."
            
            # 새로운 "fender" 레이아웃 컨테이너 찾기
            posts_selectors = [
                "div.GgwGYVzOUr_7Xzt0T0mI", # [신규]
                "div.X91NYa7h9SUdFslwWPfv"
            ]
            posts_elems = []
            for selector in posts_selectors:
                posts_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                if posts_elems: break
            
            for i, p in enumerate(posts_elems, 1):
                try:
                    # 1. 제목 및 URL
                    title_elem = None
                    title_selectors = [
                        "a.P_gXr2Vm5cF3ms_AxCoa", # [신규]
                        "a.xB7GMuBWFEZ36I3LWUaT"
                    ]
                    for selector in title_selectors:
                        try:
                            title_elem = p.find_element(By.CSS_SELECTOR, selector)
                            if title_elem: break
                        except: continue
                    
                    if not title_elem: continue
                    
                    title = title_elem.text.strip()
                    link = title_elem.get_attribute("href")
                    
                    # 2. 작성자 (sds-comps-profile-info-title-text)
                    author = "익명"
                    try:
                        author_selectors = [
                            "span.sds-comps-profile-info-title-text", 
                            "a.fender-ui_475445f0"
                        ]
                        for selector in author_selectors:
                            try:
                                author_elem = p.find_element(By.CSS_SELECTOR, selector)
                                author = author_elem.text.strip()
                                if author: break
                            except: continue
                    except: pass
                    
                    # 3. 작성일 (sds-comps-profile-info-subtext)
                    date = "-"
                    try:
                        date_elem = p.find_element(By.CSS_SELECTOR, "span.sds-comps-profile-info-subtext")
                        date = date_elem.text.strip()
                    except: pass

                    # 4. 본문 내용 스니펫 (fds-ugc-ellipsis2 또는 ellipsis3)
                    content_snippet = ""
                    try:
                        snippet_selectors = [
                            "a.J2Adx7q2a75Tzko9CKUg", # [신규]
                            "a.bhtEUbeVrksNEEpsP4DX", 
                            "span.sds-comps-text-type-body1", 
                            ".fds-ugc-ellipsis2", 
                            ".fds-ugc-ellipsis3"
                        ]
                        for selector in snippet_selectors:
                            try:
                                content_snippet = p.find_element(By.CSS_SELECTOR, selector).text.strip()
                                if content_snippet: break
                            except: continue
                    except: pass

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
