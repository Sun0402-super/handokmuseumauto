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

def run_google_maps_crawler(api_key=None, use_sentiment=False, use_summary=True):
    """구글 검색 결과 지식패널 기반 리뷰 크롤링 (사용자 가이드 + 실시간 검증 반영)"""
    target_url = "https://www.google.com/search?q=%ED%95%9C%EB%8F%85%EC%9D%98%EC%95%BD%EB%B0%95%EB%AC%BC%EA%B4%80&oq=%ED%95%9C%EB%8F%85%EC%9D%98%EC%95%BD%EB%B0%95%EB%AC%BC%EA%B4%80&gs_lcrp=EgZjaHJvbWUyBggAEEUYOdIBCDU1NTFqMGoxqAIAsAIA&sourceid=chrome&ie=UTF-8&sei=tCy-abf0PJm6vr0P3sK7kQg#wptab=si:AL3DRZHrmvnFAVQPOO2Bzhf8AX9KZZ6raUI_dT7DG_z0kV2_xxGXFzdpM9Xyfvvd96CVgXQrG_A6bF4N7od-koqrcKJxPjqI3rdVa_vpq-ZVWc08Y0HOpu7DqKZIRKxXaNGlYERbqi_LKi-eVRDZlRDGDfjw9bp87w%3D%3D"
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
        
        # 1. URL 접속 (사용자 지정 링크)
        yield f"지정된 링크로 접속합니다: {target_url}"
        driver.get(target_url)
        time.sleep(3)
        yield {"type": "screenshot", "data": capture_screenshot(driver)}
        
        # 2. 리뷰 버튼 클릭 (다각도 XPath 시도)
        yield "'리뷰' 버튼을 클릭합니다..."
        review_clicked = False
        review_xpaths = [
            "//span[contains(@class, 'REySof')]//span[text()='리뷰']", # 사용자 제공
            "//a[contains(@class, 'Y8usp') and .//span[text()='리뷰']]", # 변형 구조
            "//span[text()='리뷰' and contains(@class, 'b0Xfjd')]", # 사용자 제공 클래스
            "//a[contains(., '리뷰') and contains(@class, 'NQyKp')]", # 실시간 확인 클래스
            "//span[contains(text(), '리뷰')]/ancestor::a", # 텍스트 기준
            "//*[@role='tab']//span[text()='리뷰']" # 역할 기준
        ]
        
        for xpath in review_xpaths:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    review_clicked = True
                    yield f"   - '리뷰' 버튼 클릭 성공 (XPath: {xpath})"
                    break
            except: continue
        
        if not review_clicked:
            yield "⚠️ '리뷰' 버튼을 찾지 못해 현재 페이지에서 수집을 시도합니다."
        else:
            time.sleep(3)

        # 3. '전체' 필터 및 '최신순' 정렬 클릭
        # '전체' 클릭
        yield "'전체' 필터를 클릭합니다..."
        try:
            all_filter_xpaths = [
                "//div[contains(@class, 'niO4u')]//span[text()='전체']",
                "//span[@class='pAn7ne' and text()='전체']",
                "//*[text()='전체' and contains(@class, 'pAn7ne')]"
            ]
            for xpath in all_filter_xpaths:
                try:
                    btn = driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        yield "   - '전체' 필터 클릭 성공"
                        time.sleep(1)
                        break
                except: continue
        except: pass

        # '최신순' 클릭 (정렬 버튼이 먼저 필요한 경우 대응)
        try:
            sort_menu = driver.find_elements(By.XPATH, "//div[@role='button' and (contains(., '정렬') or contains(., 'Sort'))]")
            if sort_menu:
                driver.execute_script("arguments[0].click();", sort_menu[0])
                time.sleep(1)
        except: pass

        yield "'최신순' 정렬을 시도합니다..."
        sort_clicked = False
        sort_xpaths = [
            "//div[contains(@class, 'niO4u')]//span[contains(text(), '최신순')]",
            "//span[@class='pAn7ne']//span[text()='최신순']",
            "//*[text()='최신순' and contains(@class, 'pAn7ne')]",
            "//div[contains(@class, 'YCQwEb') and contains(., '최신순')]",
            "//span[contains(text(), '최신순')]/ancestor::div[@role='menuitemradio']"
        ]
        
        for xpath in sort_xpaths:
            try:
                sort_btn = driver.find_element(By.XPATH, xpath)
                if sort_btn.is_displayed():
                    driver.execute_script("arguments[0].click();", sort_btn)
                    sort_clicked = True
                    yield f"   - '최신순' 정렬 적용 완료 ({xpath})"
                    time.sleep(3)
                    yield {"type": "screenshot", "data": capture_screenshot(driver)}
                    break
            except: continue

        # 4. 리뷰 수집 시작
        yield "데이터 수집을 시작합니다. (상위 10개)"
        
        # 더보기 클릭 (본문 전체 보기)
        try:
            expand_btns = driver.find_elements(By.CSS_SELECTOR, "a.MtCSLb, a.LkLjB, a.P8vawd, .w8nwRe")
            for btn in expand_btns:
                try:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                except: pass
        except: pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 5. 데이터 추출 (사용자 제공 클래스 + 실시간 확인 클래스 하이브리드)
        # 리뷰 아이템 컨테이너 후보들
        container_selectors = [
            'div.bwb7ce', # 사용자 제공
            'div.p7f0Nd', # 실시간 확인
            'div[jsname="ShBeI"]', # 구정 jsname
            'div.g.kNoSve', # 변형 구조
            'div.j9vkvb' # 변형 구조
        ]
        
        containers = []
        for sel in container_selectors:
            containers = soup.select(sel)
            if containers:
                yield f"   - 리뷰 컨테이너 찾음 ({sel}: {len(containers)}개)"
                break
        
        if not containers:
            # 최종 수단: 작성자 클래스 기준 부모 찾기
            author_tags = soup.select('.Vpc5Fe, .d4r55, .TSZ61d')
            containers = [a.find_parent('div', recursive=True) for a in author_tags]
            containers = [c for c in containers if c]
            if containers: yield f"   - 작성자 기준 컨테이너 추출 ({len(containers)}개)"

        count = 0
        for container in containers:
            if count >= 10: break
            try:
                # 1. 작성자
                author = "알 수 없음"
                # Vpc5Fe(사용자), d4r55(일반), TSZ61d(실시간)
                author_tag = container.select_one('.Vpc5Fe, .d4r55, .TSZ61d, span[class*="author"]')
                if author_tag: author = author_tag.get_text(strip=True)
                
                # 2. 작성일 및 별점
                date_text = "-"
                # y3Ibjb(사용자), rsqaWe(일반)
                date_tag = container.select_one('.y3Ibjb, .rsqaWe, span[class*="date"]')
                if date_tag: date_text = date_tag.get_text(strip=True)

                # 별점 추출 (aria-label 활용)
                rating = "5" # 기본값
                rating_tag = container.select_one('span[aria-label*="별점"], span[aria-label*="별표"], span[aria-label*="stars"]')
                if rating_tag:
                    label = rating_tag.get('aria-label', '')
                    digits = re.findall(r'\d+', label)
                    if digits: rating = digits[0]
            
                # 3. 본문 내용
                content = ""
                # OA1nbd(사용자), wiI7pd(일반)
                content_tag = container.select_one('.OA1nbd, .wiI7pd, .fCH9yc')
                if content_tag:
                    content = content_tag.get_text(separator=' ', strip=True).replace("더보기", "").strip()
                
                if not content:
                    # 메타 태그 등에서 추출 시도
                    meta_tag = container.select_one('div.fjB0Xb, div.m6QErb')
                    if meta_tag: content = meta_tag.get_text(strip=True)

                if not content: continue # 본문이 아예 없으면 제외

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
                continue
            
        if count == 0:
            yield "❌ 수집된 리뷰가 없습니다. 구글 레이아웃이 변경되었을 수 있습니다."
            
    except Exception as e:
        yield f"구글 리뷰 오류 발생: {str(e)}"
    finally:
        if driver:
            try: driver.quit()
            except: pass

if __name__ == "__main__":
    for item in run_google_maps_crawler():
        print(item)
