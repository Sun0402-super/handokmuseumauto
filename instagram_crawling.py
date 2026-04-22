import time
import random
import sys
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver_utils import setup_chrome_driver, capture_screenshot
from sentiment_utils import analyze_sentiment

def handle_insta_popups(driver):
    """인스타그램의 각종 팝업(정보 저장, 알림 설정 등)을 닫습니다."""
    for _ in range(2):
        try:
            # '나중에 하기', 'Not Now', '정보 저장 안 함' 등의 버튼 검색
            pop_btns = driver.find_elements(By.XPATH, "//button[contains(text(), '나중에 하기') or contains(text(), 'Not Now') or contains(text(), '정보 저장')] | //div[@role='dialog']//button")
            for btn in pop_btns:
                try:
                    text = btn.text.strip().lower()
                    if any(x in text for x in ['나중에', 'not now', '정보 저장']):
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(1.5)
                except: continue
        except: pass

def instagram_login(driver, username, password):
    """
    인스타그램 로그인 처리 (자동 로그인 + 수동 대기 폴백)
    배포 환경(Linux)에서는 수동 대기가 불가능하므로 자동 로그인만 시도합니다.
    """
    is_cloud = sys.platform != 'win32'
    yield f"     [로그인] {sys.platform} 환경 확인 (Cloud 여부: {is_cloud})"
    
    yield "     [로그인] 인스타그램 메인 페이지 접속 중..."
    driver.get("https://www.instagram.com/")
    yield {"type": "screenshot", "data": capture_screenshot(driver)}
    wait = WebDriverWait(driver, 15)
    
    # 0. 비정상 접근 차단 확인
    if "인스타그램 사용이 일시적으로 제한되었습니다" in driver.page_source or "Try again later" in driver.page_source:
        yield "     [오류] 인스타그램으로부터 접근이 차단되었습니다. (IP 차단 가능성)"
        return False

    # 1. 이미 로그인되어 있는지 확인
    try:
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//*[@aria-label='홈' or @aria-label='Home'] | //*[@aria-label='검색' or @aria-label='Search'] | //a[contains(@href, '/direct/inbox/')]"
        )))
        yield "     [로그인] 이미 로그인되어 있습니다."
        handle_insta_popups(driver) 
        return True
    except:
        yield "     [로그인] 로그인 상태가 아님을 확인했습니다."

    # 2. 자동 로그인 시도 (아이디/비번이 있는 경우)
    if username and password:
        try:
            # 입력창 대기
            user_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@name='username'] | //input[@aria-label='Phone number, username, or email']")))
            pass_input = driver.find_element(By.XPATH, "//input[@name='password'] | //input[@aria-label='Password']")
            
            user_input.send_keys(username)
            pass_input.send_keys(password)
            time.sleep(1)
            
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_btn.click()
            yield "     [로그인] 로그인 정보를 입력했습니다. 인증 확인 중..."
            time.sleep(7) 
            yield {"type": "screenshot", "data": capture_screenshot(driver)}
            
            # 2단계 인증/보안 코드 확인창이 떴는지 체크
            if "checkpoint" in driver.current_url:
                yield "     [주의] 인스타그램 보안 확인(2단계 인증 등)이 필요합니다."
                if is_cloud:
                    yield "     [오류] 클라우드 서버에서는 보안 인증을 직접 수행할 수 없습니다."
                    return False

            handle_insta_popups(driver)
            
            # 최종 로그인 성공 확인
            try:
                wait.until(EC.presence_of_element_located((
                    By.XPATH, "//*[@aria-label='홈' or @aria-label='Home'] | //*[@aria-label='검색' or @aria-label='Search']"
                )))
                yield "     [로그인] 자동 로그인 성공!"
                return True
            except:
                pass
            
        except Exception as e:
            yield f"     [로그인] 자동 로그인 실패: {e}"
            if is_cloud:
                yield "     [원인] Streamlit Cloud(리눅스 서버)에서는 인스타그램이 자동화 도구(빗)를 감지하여 로그인을 차단합니다."
                yield "     [해결방안 1] 로심 PC에서 정규 Chrome으로 인스타그램 로그인 후, 데이터를 로컴 Streamlit으로 수집하세요."
                yield "     [해결방안 2] 먹한끄.윤드인 등 판매사이트의 인스타그램 수켜지를 직접 사용하는 방법도 확인하세요."

    # 3. 수동 로그인 대기 (아이디/비번이 없거나 자동 로그인이 실패한 경우)
    if is_cloud:
        yield "     ⚠️ [인스타그램 수집 불가 안내]"
        yield "     Streamlit Cloud(리눅스 서버)에서는 인스타그램 로그인이 불가능합니다."
        yield "     📌 원인: 인스타그램은 클라우드 서버 IP + Selenium 자동화를 감지하여 차단합니다."
        yield "     💡 해결방법:"
        yield "        1. 로컬 PC에서 Streamlit을 실행하면 수동 로그인 후 수집 가능합니다."
        yield "           (run_app.bat 실행 → 브라우저에서 직접 로그인)"
        yield "        2. 인스타그램 공식 해시태그 페이지에서 직접 후기를 모니터링하세요."
        yield "           👉 https://www.instagram.com/explore/tags/한독의약박물관/"
        yield "     📋 현재 네이버 블로그, 카카오맵, Google 지도 수집은 정상 동작 중입니다."
        return False

    yield "**************************************************************"
    yield "     [중요] 브라우저 창에서 직접 인스타그램에 로그인해 주세요!!"
    yield "     실시간 화면(Live View)을 보면서 인증을 완료할 수 있습니다."
    yield "**************************************************************"
    
    # 5분간 5초 주기로 로그인 상태 체크하며 스크린샷 갱신
    for i in range(60): # 5 * 60 = 300초
        try:
            # 로그인 성공 요소가 있는지 확인 (짧은 대기)
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//*[@aria-label='홈' or @aria-label='Home'] | //*[@aria-label='검색' or @aria-label='Search'] | //a[contains(@href, '/direct/inbox/')]"))
            )
            yield "     [로그인] 수동 로그인 완료 확인."
            yield {"type": "screenshot", "data": capture_screenshot(driver)}
            time.sleep(3)
            return True
        except:
            # 아직 로그인 중이면 스크린샷만 업데이트
            yield {"type": "screenshot", "data": capture_screenshot(driver)}
            if i % 6 == 0: # 30초마다 남은 시간 알림
                yield f"     [로그인] 대기 중... ({300 - i*5}초 남음)"
    
    yield "     [오류] 제한 시간 내에 로그인이 완료되지 않았습니다."
    return False

def _extract_post_data(driver, soup, author_name_filter=None):
    """게시물 페이지에서 데이터를 추출하는 내부 헬퍼 함수"""
    # 작성자 (헤더 섹션에서 실제 계정명 추출)
    author_name = "알 수 없음"
    # 헤더 내의 링크 텍스트, 또는 특정 클래스들 시도
    author_selectors = [
        'header a._a6hd',
        'div._a9zr h2 a',
        'header a[href*="/"] span',
        'header a[role="link"]:not([href="/"])',
        'div[role="button"] a.x1i10hfl',
        'a.x1i10hfl[role="link"] span',
        'span._ap3a._aaco._aacw._aacx._aad7._aade'
    ]
    for sel in author_selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            author_name = tag.get_text(strip=True)
            break
    
    # 예외: 만약 계정명이 'Instagram'으로 수집되면 다른 패턴 시도
    if author_name in ["Instagram", "알 수 없음"] or not author_name:
        alt_author = soup.select_one('div._aa-b a, div.x1i10hfl a, a.x1i10hfl span')
        if alt_author:
            author_name = alt_author.get_text(strip=True)

    # 본문: 최근 인스타그램 레이아웃 및 범용 클래스 반영
    content_tag = soup.select_one('h1._ap3a, div._a9zr, div._a9zs, ._aade, h1, div[dir="auto"]')
    content = content_tag.get_text(separator=' ', strip=True) if content_tag else ""
    
    # 본문 처음에 계정명이 포함되어 있을 경우 철저히 제거
    # 인스타그램 웹은 본문 div 제일 앞에 <a>계정명</a>이 붙어 나오는 경우가 많음
    if content.lower().startswith(author_name.lower()):
        content = content[len(author_name):].strip()
    
    # 날짜 (ISO 포맷)
    date_tag = soup.select_one('time[datetime]')
    date_str = date_tag.get('datetime', '') if date_tag else ""
    
    # URL (driver.current_url이 location/explore 주소인 경우 대비)
    post_url = driver.current_url
    if "/p/" not in post_url and "/reels/" not in post_url:
        # 모달 내부의 시간 태그가 링크를 포함하고 있음
        link_tag = soup.select_one('time[datetime]').find_parent('a') if date_tag else None
        if link_tag and link_tag.get('href'):
            inner_href = link_tag.get('href')
            post_url = f"https://www.instagram.com{inner_href}"
    
    return {
        "작성자": author_name,
        "본문내용": content,
        "작성일": date_str,
        "URL": post_url
    }

def crawl_hashtag(driver, hashtag, max_posts=10, api_key=None, use_sentiment=False, use_summary=True):
    """해당 해시태그의 게시물 수집"""
    url = f"https://www.instagram.com/explore/tags/{hashtag}/"
    driver.get(url)
    time.sleep(random.uniform(5, 7))
    
    # [추가] 로그인 페이지 리디렉션 확인
    if "accounts/login" in driver.current_url:
        yield "🚨 [로그인 필요] 인스타그램이 해시태그 검색을 위해 로그인을 요청합니다."
        yield "💡 로컬 환경이라면 수집 설정을 통해 로그인을 완료한 뒤 다시 시도해 주세요."
        return

    try:
        # '최근 게시물' 탭 찾아서 클릭 (해시태그 화면 대응)
        print("     [인스타그램] 해시태그 '최근' 탭으로 전환 중...")
        recent_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[text()='최근']/ancestor::a | //div[@role='tablist']//div[contains(text(), '최근') or contains(text(), 'Recent')] | //a[contains(@href, '/recent/')]"))
        )
        recent_tab.click()
        time.sleep(5)
        yield {"type": "screenshot", "data": capture_screenshot(driver)}
    except Exception as e:
        print(f"     [주의] 해시태그 '최근' 탭 전환 실패 (계속 진행): {e}")

    yield from _collect_posts(driver, max_posts, api_key, use_sentiment, use_summary)

def crawl_tagged_posts(driver, handle="handokmuseum", max_posts=10, api_key=None, use_sentiment=False, use_summary=True):
    """공식 계정(@handokmuseum)의 '태그됨' 탭에서 게시물 수집"""
    url = f"https://www.instagram.com/{handle}/tagged/"
    driver.get(url)
    time.sleep(random.uniform(5, 7))
    
    if "accounts/login" in driver.current_url:
        yield f"🚨 [로그인 필요] @{handle}의 태그된 게시물 접근을 위해 로그인이 필요합니다."
        return

    yield f"     [인스타그램] @{handle} 공식 계정 '태그됨' 탭 분석 중..."
    yield {"type": "screenshot", "data": capture_screenshot(driver)}
    
    yield from _collect_posts(driver, max_posts, api_key, use_sentiment, use_summary)

def crawl_location(driver, location_id="109120676658159", max_posts=10, api_key=None, use_sentiment=False, use_summary=True):
    """특정 장소의 게시물을 최신순으로 수집"""
    url = f"https://www.instagram.com/explore/locations/{location_id}/"
    driver.get(url)
    time.sleep(random.uniform(5, 7))
    
    if "accounts/login" in driver.current_url:
        yield "🚨 [로그인 필요] 인스타그램이 장소 검색을 위해 로그인을 요청합니다."
        yield "💡 이미 로그인했는데도 이 메시지가 보인다면 계정이 일시적으로 제한된 상태일 수 있습니다."
        return

    try:
        print("     [인스타그램] '최근 게시물' 탭으로 전환 중...")
        recent_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[text()='최근']/ancestor::a | //div[@role='tablist']//div[contains(text(), '최근') or contains(text(), 'Recent')] | //a[contains(@href, '/recent/')]"))
        )
        recent_tab.click()
        time.sleep(5)
        yield {"type": "screenshot", "data": capture_screenshot(driver)}
    except Exception as e:
        print(f"     [주의] '최근' 탭을 찾는 데 실패했습니다. 기본 인기 게시물 순으로 진행합니다. ({e})")

    yield from _collect_posts(driver, max_posts, api_key, use_sentiment, use_summary)

def _collect_posts(driver, max_posts, api_key, use_sentiment, use_summary):
    """열려있는 인스타그램 페이지에서 게시물을 순차적으로 수집 (7일 이내 전수 수집)"""
    try:
        # 첫 번째 게시물 클릭 확인
        print("     [인스타그램] 첫 번째 게시물 여는 중...")
        first_post = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/reels/'], a[href*='/reel/']"))
        )
        driver.execute_script("arguments[0].click();", first_post)
        time.sleep(5)
        
        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)
        attempts = 0
        collected_count = 0
        
        while attempts < 100 and collected_count < max_posts: # 최대 100개까지 탐색 (안전 장치)
            attempts += 1
            try:
                time.sleep(2)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                data = _extract_post_data(driver, soup)
                
                author_name = data["작성자"]
                content = data["본문내용"]
                date_str = data["작성일"]
                
                # 1. 공식 계정 제외 및 날짜 검사
                if "handokmuseum" not in author_name.lower():
                    if date_str:
                        try:
                            # ISO 포맷 (2024-03-21T02:00:00.000Z 등)
                            post_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            
                            if post_time < one_week_ago:
                                # 최근 게시물 탭이므로, 7일 이전 게시물이 나오면 수집 종료
                                print(f"     [인스타그램] 7일 이전 게시물 발견({date_str}).")
                                break
                            
                            # 3. 감성 분석 및 추가
                            sentiment, reason = "", ""
                            if use_sentiment and content:
                                print(f"     [인스타그램] ({collected_count+1}) '{author_name}' 분석 중...")
                                sentiment, reason = analyze_sentiment(content, api_key, is_instagram=True, use_summary=use_summary)
                            
                            data.update({
                                "출처": "인스타그램",
                                "감성분석": sentiment,
                                "분석이유": reason
                            })
                            yield data
                            collected_count += 1
                        except Exception as e:
                            print(f"     [인스타그램] 날짜 파싱 오류: {e}")
                    else:
                        print("     [인스타그램] 날짜 정보를 찾을 수 없어 스킵합니다.")

                # 다음 게시물 버튼 클릭 (보강된 XPath)
                try:
                    next_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[.//svg[@aria-label='다음' or @aria-label='Next']] | //div[contains(@class, ' _aaqg ')]//button | //button[contains(@class, '_abl-')]//div[contains(@class, '_aaqg')] | //div[contains(@style, 'right')]//button"))
                    )
                    driver.execute_script("arguments[0].click();", next_btn)
                    # 전환 후 로딩 대기 (무작위)
                    time.sleep(random.uniform(2.5, 4.0))
                    yield {"type": "screenshot", "data": capture_screenshot(driver)}
                except:
                    print("     [인스타그램] 다음 게시물 버튼이 없습니다. 종료합니다.")
                    break
                
            except Exception as e:
                print(f"     [인스타그램] 게시물 추출 중 오류: {e}")
                break
                
    except Exception as e:
        print(f"     [인스타그램] 게시물 목록 접근 오류: {e}")
        
    return

if __name__ == "__main__":
    # 테스트용 (실제 실행 시 계정 정보 필요)
    print("인스타그램 크롤러 테스트 모드")
