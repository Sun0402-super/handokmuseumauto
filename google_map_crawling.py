import os
import time
import json
import random
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver_utils import setup_chrome_driver, capture_screenshot
from sentiment_utils import analyze_sentiment
from filter_utils import parse_date_to_string

def run_google_maps_crawler(api_key=None, use_sentiment=False, use_summary=True, headless=True):
    """구글 지도 리뷰 크롤링 (Google Maps 서비스 직접 접속 방식)"""
    target_url = "https://www.google.com/maps/place/%ED%95%9C%EB%8F%85%EC%9D%98%EC%95%BD%EB%B0%95%EB%AC%BC%EA%B4%80/data=!4m8!3m7!1s0x3564c801b414c031:0xae2627b4bc74c1f6!8m2!3d36.9705606!4d127.4652168!9m1!1b1!16s%2Fg%2F1trqf1gr?entry=ttu&g_ep=EgoyMDI2MDQwNi4wIKXMDSoASAFQAw%3D%3D"
    driver = None
    
    # [변경] 로컬(Windows) 환경에서는 캡차 대응을 위해 헤드리스 모드를 기본적으로 해제
    import sys
    if sys.platform == 'win32' and headless:
        headless = False
        yield "⚠️ 로컬 환경 감지: 캡차 대응을 위해 브라우저 창을 활성화합니다."

    try:
        yield "스텔스 모드로 브라우저를 시작합니다..."
        driver, status = setup_chrome_driver(headless=headless)
        if not driver:
            yield "❌ 크롬 브라우저를 시작할 수 없습니다."
            return
            
        driver.set_page_load_timeout(40)
        wait = WebDriverWait(driver, 20)
        
        # 1. URL 접속
        yield f"구글 지도로 직접 접속합니다... "
        driver.get(target_url)
        time.sleep(random.uniform(5.0, 7.0))
        
        # [추가] 로봇 확인(CAPTCHA) 감지
        if "google.com/sorry" in driver.current_url or "robot" in driver.page_source.lower():
            yield "🚨 [검증 필요] 구글에서 로봇 확인을 요청하고 있습니다."
            if not headless:
                yield "💡 화면에 뜬 브라우저 창에서 직접 '로봇이 아닙니다'를 클릭해 주세요. (60초 대기 시작)"
                time.sleep(60)
                yield "   - 대기 완료. 수집을 계속 진행합니다."
                time.sleep(3)
            else:
                yield "❌ 헤드리스 모드라 캡차를 해결할 수 없습니다. 잠시 후 검색 옵션에서 '브라우저 숨기기'를 해제하고 다시 시도해 주세요."
                return

        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        # 2. '리뷰' 버튼 클릭
        yield "'리뷰' 탭으로 이동합니다..."
        try:
            # 텍스트 '리뷰'를 포함한 요소 찾기
            review_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'Gpq6kf') and text()='리뷰'] | //button[.//div[text()='리뷰']]")))
            driver.execute_script("arguments[0].click();", review_tab)
            time.sleep(random.uniform(2.0, 3.0))
            yield "   - '리뷰' 탭 클릭 성공"
        except Exception as e:
            yield f"   - [정보] '리뷰' 탭이 이미 활성화되어 있거나 찾을 수 없습니다. (계속 진행)"

        # 3. '정렬' 클릭
        yield "정렬 메뉴를 엽니다..."
        try:
            sort_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(@class, 'GMtm7c') and text()='정렬'] | //button[contains(@aria-label, '리뷰 정렬')]")))
            driver.execute_script("arguments[0].click();", sort_btn)
            time.sleep(random.uniform(1.5, 2.5))
            
            # 4. '최신순' 클릭
            yield "'최신순' 정렬을 적용합니다..."
            latest_opt = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'mLuXec') and text()='최신순'] | //div[@role='menuitemradio' and .//div[text()='최신순']]")))
            driver.execute_script("arguments[0].click();", latest_opt)
            time.sleep(random.uniform(3.0, 4.5))
            yield "   - 최신순 정렬 완료"
        except Exception as e:
            yield f"   - [주의] 정렬 설정 실패 (기본 순으로 진행): {e}"

        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        # 5. 리뷰 수집 시작
        yield "데이터 추출을 위해 페이지를 분석 중입니다..."
        
        # 자세히 보기(더보기) 버튼들 확장
        try:
            expand_btns = driver.find_elements(By.XPATH, "//button[text()='자세히 보기' or text()='더보기' or @aria-label='더보기']")
            if expand_btns:
                for btn in expand_btns[:10]: # 상위 10개만 우선 시도
                    try:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                    except: pass
                time.sleep(1)
        except: pass

        # BeautifulSoup으로 파싱
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        review_elements = soup.select('div.jftiEf')
        
        yield f"   - {len(review_elements)}개의 리뷰 컨테이너를 찾았습니다."

        count = 0
        for el in review_elements:
            if count >= 10: break
            try:
                # 1. 작성자
                author = "알 수 없음"
                author_tag = el.select_one('div.d4r55.fontTitleMedium')
                if author_tag: author = author_tag.get_text(strip=True)
                
                # 2. 작성일
                date_text = "-"
                date_tag = el.select_one('span.rsqaWe')
                if date_tag: date_text = date_tag.get_text(strip=True)

                # 3. 별점
                rating = "5"
                rating_tag = el.select_one('span.kvMYJc')
                if rating_tag:
                    label = rating_tag.get('aria-label', '')
                    digits = re.findall(r'\d+', label)
                    if digits: rating = digits[0]
            
                # 4. 본문 내용
                content = ""
                content_tag = el.select_one('span.wiI7pd')
                if content_tag:
                    content = content_tag.get_text(separator=' ', strip=True).strip()

                if not content: continue # 내용이 없으면 건너뜀

                count += 1
                sentiment, reason = "", ""
                if use_sentiment:
                    yield f"   ({count}/10) '{author}' 리뷰 분석 중..."
                    sentiment, reason = analyze_sentiment(content, api_key, use_summary=use_summary, rating=rating)
                
                yield {
                    "출처": "구글 리뷰",
                    "작성자": author,
                    "제목": "구글 리뷰",
                    "작성일": parse_date_to_string(date_text),
                    "별점": rating,
                    "방문일": "",
                    "감성분석": sentiment,
                    "분석이유": reason,
                    "본문내용": content
                }
            except Exception as e:
                print(f"     [오류] 개별 리뷰 파싱 실패: {e}")
                continue
            
        if count == 0:
            yield "❌ 유효한 리뷰 데이터를 추출하지 못했습니다."
            
    except Exception as e:
        yield f"구글 리뷰 오류 발생: {str(e)}"
    finally:
        if driver:
            try: driver.quit()
            except: pass

if __name__ == "__main__":
    for item in run_google_maps_crawler():
        print(item)
