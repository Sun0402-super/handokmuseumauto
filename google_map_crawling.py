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
from filter_utils import parse_date_to_string, is_within_one_week

def run_google_maps_crawler(api_key=None, use_sentiment=False, use_summary=True, headless=True):
    """구글 지도 리뷰 크롤링 (Google Maps 서비스 직접 접속 방식)"""
    target_url = "https://www.google.com/maps/place/%ED%95%9C%EB%8F%85%EC%9D%98%EC%95%BD%EB%B0%95%EB%AC%BC%EA%B4%80/data=!4m8!3m7!1s0x3564c801b414c031:0xae2627b4bc74c1f6!8m2!3d36.9705606!4d127.4652168!9m1!1b1!16s%2Fg%2F1trqf1gr"
    driver = None
    
    # [시스템] 운영체제 및 모드 확인
    import sys
    yield f"     [시스템] 운영체제: {sys.platform}, 현재 모드: {'브라우저 숨김' if headless else '브라우저 표시'}"
    
    if sys.platform == 'win32' and headless:
        yield "ℹ️ 현재 '브라우저 숨김' 모드입니다. 캡차 발생 시 해결이 어려울 수 있습니다."

    try:
        yield "스텔스 모드로 브라우저를 시작합니다..."
        driver, status = setup_chrome_driver(headless=headless)
        if not driver:
            yield "❌ 크롬 브라우저를 시작할 수 없습니다."
            return
            
        driver.set_page_load_timeout(120) # 기존 40초에서 120초로 대폭 연장
        wait = WebDriverWait(driver, 30)
        
        # 1. URL 접속
        yield f"구글 지도로 직접 접속합니다..."
        try:
            driver.get(target_url)
        except Exception as te:
            # 타임아웃이 발생해도 DOM이 일부 로드되었을 수 있으므로 계속 시도
            yield f"     [주의] 페이지 로딩 시간 초과 발생 (계속 진행 시도): {str(te)[:50]}..."
            time.sleep(5)
            
        # [추가] 로봇 확인(CAPTCHA) 감지
        # 여러 패턴(URL, 페이지 제목, 특정 텍스트)으로 감지
        is_captcha = False
        try:
            is_captcha = "google.com/sorry" in driver.current_url or \
                         "비정상적인 트래픽" in driver.page_source
        except: pass
                     
        if is_captcha:
            yield "🚨 [검증 필요] 구글에서 로봇 확인(CAPTCHA)을 요청하고 있습니다."
            if not headless:
                yield "💡 화면에 뜬 브라우저 창에서 직접 '로봇이 아닙니다'를 클릭해 주세요. (60초 대기)"
                # 캡차 해결 여부를 실시간으로 모니터링 (최대 60초)
                solved = False
                for _ in range(12): # 5초 * 12 = 60초
                    time.sleep(5)
                    if "google.com/sorry" not in driver.current_url and "robot" not in driver.page_source.lower():
                        solved = True
                        break
                
                if solved:
                    yield "   - 캡차 해결 확인. 수집을 계속합니다."
                else:
                    yield "   - 시간 초과: 캡차가 해결되지 않았습니다. 수집이 중지될 수 있습니다."
            else:
                yield "❌ 현재 '브라우저 숨기기' 모드입니다. 캡차를 해결하려면 수집기 왼쪽 설정에서 '브라우저 숨기기'를 해제하고 다시 실행해 주세요."
                return

        yield {"type": "screenshot", "data": capture_screenshot(driver)}

        # 2. '리뷰' 탭 확인 및 클릭
        yield "리뷰 데이터 로딩 중..."
        try:
            # 이미 리뷰 탭일 수도 있으므로 컨테이너 확인
            if len(driver.find_elements(By.CLASS_NAME, "jftiEf")) > 0:
                yield "   - 리뷰 데이터가 이미 표시되어 있습니다."
            else:
                review_xpath = "//div[contains(@class, 'Gpq6kf') and text()='리뷰'] | //button[contains(@aria-label, '리뷰')] | //button[.//div[text()='리뷰']]"
                review_tab = wait.until(EC.element_to_be_clickable((By.XPATH, review_xpath)))
                driver.execute_script("arguments[0].click();", review_tab)
                time.sleep(random.uniform(2.0, 3.5))
                yield "   - '리뷰' 탭 활성화 성공"
        except Exception:
            yield "   - [정보] 리뷰 탭이 이미 활성 상태이거나 자동 로드되었습니다."

        # 3. '최신순' 정렬 적용
        yield "최신순으로 정렬을 변경합니다..."
        try:
            # 정렬 버튼 클릭: '정렬'이라는 텍스트를 포함하거나 aria-label에 '정렬'이 있는 버튼
            sort_xpath = "//button[contains(@aria-label, '정렬') or contains(., '정렬')]"
            sort_btn = wait.until(EC.element_to_be_clickable((By.XPATH, sort_xpath)))
            driver.execute_script("arguments[0].click();", sort_btn)
            time.sleep(random.uniform(1.5, 2.5))
            
            # '최신순' 옵션 클릭: 팝업 메뉴 내 '최신'이라는 단어가 포함된 요소
            latest_xpath = "//div[@role='menuitemradio' and contains(., '최신')] | //div[contains(text(), '최신순')] | //div[contains(text(), '최신')]"
            # 화면에 보이는 요소 중 하나를 선택
            options = driver.find_elements(By.XPATH, latest_xpath)
            clicked = False
            for opt in options:
                if opt.is_displayed():
                    driver.execute_script("arguments[0].click();", opt)
                    clicked = True
                    break
            
            if not clicked:
                raise Exception("최신순 옵션을 클릭할 수 없습니다.")
                
            time.sleep(random.uniform(3.0, 4.5))
            yield "   - 최신순 정렬 완료"
        except Exception as e:
            yield f"   - [정보] 정렬 설정 스킵 (기본 순서 진행): {str(e)[:50]}"

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
                author_tag = el.select_one('div.d4r55') # .fontTitleMedium 제거
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

                if not content: continue

                # [필터] 크롤링 날짜 기준 7일 초과 리뷰 제외
                if not is_within_one_week(date_text):
                    continue

                count += 1
                sentiment, reason = "", ""
                if use_sentiment:
                    yield f"   ({count}/{min(len(review_elements), 10)}) '{author}' 리뷰의 감성을 분석 중..."
                    sentiment, reason = analyze_sentiment(content, api_key, use_summary=use_summary, rating=rating)
                
                yield {
                    "출처": "구글 리뷰",
                    "작성자": author,
                    "제목": "구글 리뷰",
                    "작성일": parse_date_to_string(date_text),
                    "별점": rating,
                    "감성분석": sentiment,
                    "분석이유": reason,
                    "본문내용": content
                }
            except Exception:
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
