import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver_utils import setup_chrome_driver, capture_screenshot
from filter_utils import parse_date_to_string
from sentiment_utils import analyze_sentiment

def crawl_kakao_map(api_key=None, use_sentiment=False, use_summary=True, headless=True):
    """
    카카오맵(다음 지도) 리뷰를 Chrome 브라우저로 크롤링하는 제너레이터입니다.
    대상: 한독의약박물관 (ID: 10949300)
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

        # 1. 카카오맵 리뷰 페이지 직접 접속
        url = "https://place.map.kakao.com/10949300#review"
        driver.get(url)
        time.sleep(3) # 로딩 대기
        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        yield "카카오맵 리뷰 목록 추출 중..."
        
        # 2. '최신 순' 정렬 클릭 추가
        yield "'최신 순' 정렬을 선택합니다..."
        try:
            # 현재 정렬 상태 확인
            sort_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn_sort")))
            current_sort = sort_btn.find_element(By.CSS_SELECTOR, "strong.tit_sort").text.strip()
            
            if "최신 순" not in current_sort:
                # 정렬 레이어 열기
                driver.execute_script("arguments[0].click();", sort_btn)
                time.sleep(1.5)
                
                # '최신 순' 링크 찾아서 클릭
                # XPath가 더 정확할 수 있음
                newest_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'link_sort') and contains(., '최신 순')]")))
                driver.execute_script("arguments[0].click();", newest_link)
                
                # 정렬 반영 대기
                time.sleep(2.5)
                
                # 결과 다시 확인 (검증)
                new_sort = driver.find_element(By.CSS_SELECTOR, "button.btn_sort strong.tit_sort").text.strip()
                if "최신 순" in new_sort:
                    yield "   - ✅ '최신 순' 정렬이 성공적으로 적용되었습니다."
                else:
                    yield f"   - ⚠️ '최신 순' 적용 시도했으나 현재 상태: {new_sort}"
            else:
                yield "   - 이미 '최신 순'으로 정렬되어 있습니다."
        except Exception as e:
            yield f"   - [주의] 정렬 버튼 클릭 실패 (기본값으로 진행): {e}"

        # 3. 리뷰 "더보기" 클릭 (전체 로드용)
        try:
            more_btn = driver.find_element(By.CSS_SELECTOR, "a.link_more")
            if more_btn.is_displayed():
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(1.5)
        except: pass

        # 4. 개별 리뷰 "더보기" (본문 펼치기) 클릭
        more_content_btns = driver.find_elements(By.CSS_SELECTOR, "span.btn_more")
        for btn in more_content_btns:
            try:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
            except: pass
        time.sleep(1)

        # 5. 리뷰 요소 추출
        # list_review 내의 li 요소들을 순회합니다.
        review_items = driver.find_elements(By.CSS_SELECTOR, "ul.list_review > li")
        
        results_count = 0
        for i, item in enumerate(review_items):
            if results_count >= 10: break # 상위 10개만
            
            try:
                # 1. 작성자
                author = "익명"
                try:
                    # name_user 내부의 text만 추출 (screen_out 제외)
                    name_elem = item.find_element(By.CSS_SELECTOR, "span.name_user")
                    author = driver.execute_script("return arguments[0].lastChild.textContent;", name_elem).strip()
                except: pass
                
                # 2. 작성일
                date = "-"
                try:
                    date_elem = item.find_element(By.CSS_SELECTOR, "span.txt_date")
                    date = date_elem.text.strip()
                except: pass
                
                # 3. 별점
                rating = "5"
                try:
                    # starred_grade 내의 두 번째 screen_out에 숫자(5.0 등)가 있음
                    # Selenium .text는 숨겨진 텍스트를 가져오지 못하므로 textContent 사용
                    rating_elems = item.find_elements(By.CSS_SELECTOR, ".starred_grade .screen_out")
                    if len(rating_elems) >= 2:
                        rating = rating_elems[1].get_attribute("textContent").strip()
                    elif rating_elems:
                        rating = rating_elems[0].get_attribute("textContent").strip().replace("별점", "").strip()
                except: pass

                # 4. 본문 내용
                content = ""
                try:
                    content_elem = item.find_element(By.CSS_SELECTOR, "p.desc_review")
                    content = content_elem.text.replace("더보기", "").strip()
                except: pass
                
                if not content and not author: continue

                # 감성 분석
                sentiment, reason = "", ""
                if use_sentiment and content:
                    # 별점이 5.0이면 바로 긍정 처리
                    if rating == "5.0" or rating == "5":
                        sentiment, reason = "긍정", "만점|별점 5점 만점 자동 분류"
                    else:
                        sentiment, reason = analyze_sentiment(content, api_key, use_summary=use_summary)

                yield {
                    "출처": "카카오맵 리뷰",
                    "작성자": author,
                    "제목": "카카오맵 리뷰",
                    "작성일": parse_date_to_string(date),
                    "URL": url,
                    "본문내용": content,
                    "감성분석": sentiment,
                    "분석이유": reason,
                    "별점": rating
                }
                results_count += 1
                
            except Exception:
                continue

        yield f"카카오맵 리뷰 수집 완료 (총 {results_count}건)"

    except Exception as e:
        yield f"카카오맵 수집 중 오류: {e}"
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    for item in crawl_kakao_map(use_sentiment=False):
        print(item)
