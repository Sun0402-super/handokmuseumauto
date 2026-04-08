import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver_utils import setup_chrome_driver, capture_screenshot
from filter_utils import parse_date_to_string
from sentiment_utils import analyze_sentiment

def crawl_daum(query, max_pages=1, api_key=None, use_sentiment=False, use_summary=True, headless=True):
    """
    다음 검색결과(통합웹/블로그)를 Chrome 브라우저로 크롤링하는 제너레이터입니다.
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

        # 1. 다음 검색 직접 접속 (최신순, 1주일 필터 파라미터 포함)
        # sort=recency (최신순), period=w (1주일)
        url = f"https://search.daum.net/search?w=fusion&q={query}&sort=recency&period=w"
        driver.get(url)
        time.sleep(4) # 레이아웃 안정화를 위해 대기 시간 증가
        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        results_count = 0
        
        for page in range(1, max_pages + 1):
            yield f"[Daum {page}페이지] 검색 결과 추출 중..."
            
            # 검색 결과 카드들 찾기
            cards = driver.find_elements(By.CSS_SELECTOR, "c-card")
            
            for card in cards:
                try:
                    # 1. 제목 및 URL (c-title 또는 strong.tit-g a)
                    title, link = "", ""
                    try:
                        title_elem = card.find_element(By.CSS_SELECTOR, "strong.tit-g a")
                        title = title_elem.text.strip()
                        link = title_elem.get_attribute("href")
                    except: pass
                    
                    if not title: continue # 제목 없으면 건너뜀

                    # 2. 작성자 (c-frag[slot='_slt1'] 또는 .item-writer)
                    author = "익명"
                    try:
                        # 검증된 선택자 우선 적용
                        author_selectors = ["c-frag[slot='_slt1']", "a.item-writer .tit_item", "span.txt_info"]
                        for sel in author_selectors:
                            try:
                                author_elem = card.find_element(By.CSS_SELECTOR, sel)
                                text = author_elem.text.strip()
                                if text and "." not in text: # 도메인 제외
                                    author = text
                                    break
                            except: continue
                    except: pass
                    
                    # 3. 작성일 (c-footer span.txt_desc)
                    date = "-"
                    try:
                        date_elem = card.find_element(By.CSS_SELECTOR, "c-footer span.txt_desc, .txt_desc")
                        date = date_elem.text.strip()
                    except: pass

                    # 4. 본문 내용 스니펫 (p.conts-desc)
                    content_snippet = ""
                    try:
                        content_elem = card.find_element(By.CSS_SELECTOR, "p.conts-desc, .conts-desc")
                        content_snippet = content_elem.text.strip()
                    except: pass

                    # 감성 분석
                    sentiment, reason = "", ""
                    if use_sentiment and content_snippet:
                        sentiment, reason = analyze_sentiment(content_snippet, api_key, use_summary=use_summary)

                    yield {
                        "출처": "Daum 검색",
                        "작성자": author,
                        "제목": title,
                        "작성일": parse_date_to_string(date),
                        "URL": link,
                        "본문내용": content_snippet,
                        "감성분석": sentiment,
                        "분석이유": reason
                    }
                    results_count += 1
                    
                except Exception:
                    continue
            
            # 다음 페이지 이동 (p=2 등 파라미터 변경 또는 버튼 클릭)
            # 여기서는 단순 1페이지 수집 우선
            if page < max_pages:
                try:
                    # 다음 페이지 버튼 찾기
                    next_btn = driver.find_element(By.CSS_SELECTOR, ".btn_next:not([disabled])")
                    driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(2)
                except:
                    break
            else:
                break

        yield f"Daum 검색 수집 완료 (총 {results_count}건)"

    except Exception as e:
        yield f"Daum 수집 중 오류: {e}"
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    for item in crawl_daum("한독의약박물관", max_pages=1):
        print(item)
