import os
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import WebDriverException
import subprocess
import sys
import shutil
from selenium.webdriver.chrome.service import Service

# 글로벌 상태 관리 (크롬이 한 번 실패하면 해당 세션 동안 Edge 우선 사용)
_CHROME_UNSTABLE = False

def setup_chrome_driver(headless=True, use_profile=True):
    """
    Chrome 브라우저 구동을 위한 공통 드라이버 설정 함수.
    """
    global _CHROME_UNSTABLE
    
    # 크롬이 이미 불안정하다고 판단된 경우 바로 Edge로 전환
    if _CHROME_UNSTABLE:
        print("     [정보] 크롬 불안정 상태 감지로 인해 Edge 브라우저를 사용합니다.")
        return setup_edge_driver(headless=headless, use_profile=use_profile)

    # [개선] 스텔스 기능 추가 (탐지 회피)
    try:
        from selenium_stealth import stealth
    except ImportError:
        stealth = None

    options = ChromeOptions()
    
    # [중요] 리눅스(Streamlit Cloud) 환경에서는 무조건 Headless 모드를 강제합니다. (창 띄우기 불가)
    is_linux = sys.platform != 'win32'
    if is_linux:
        headless = True
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--single-process')
        
        # 크로미움 바이너리 경로 탐색
        for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
            if os.path.exists(path):
                options.binary_location = path
                break
    else:
        if headless:
            options.add_argument('--headless=new')
            
    # 공동 옵션 (봇 탐지 회피 및 폰트 렌더링 최적화)
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--lang=ko')
    options.add_argument('--force-device-scale-factor=1')
    
    # 랜덤 User-Agent 설정
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ]
    options.add_argument(f'user-agent={ua_list[int(time.time()) % len(ua_list)]}')

    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(base_dir, 'chrome_profile')

    if use_profile:
        _clean_profile_locks(user_data_dir)
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--profile-directory=Default")

    try:
        if is_linux:
            # 리눅스 환경에서는 서비스 경로 명시 시도
            service_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
            service = Service(service_path)
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)

        # [중요] 스텔스 적용 (라이브러리 성공 시)
        if stealth:
            stealth(driver,
                languages=["ko-KR", "ko", "en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
        
        # [중요] CDP 명령어로 navigator.webdriver 속성 최종 제거
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        time.sleep(3) # 안정화 대기
        return driver, "SUCCESS"
            
    except Exception as e:
        print(f"     [경고] 크롬 구동 실패: {e}")
        return None, "FAILED"

def _clean_profile_locks(user_data_dir):
    """Chrome/Edge 프로필 디렉토리 내의 잠금 파일 및 활성 포트 파일을 제거합니다."""
    lock_files = ["SingletonLock", "lock", "parent.lock", "DevToolsActivePort"]
    if not os.path.exists(user_data_dir):
        return
        
    print(f"     [정리] 프로필 잠금 파일 확인 중: {user_data_dir}")
    for root, dirs, files in os.walk(user_data_dir):
        for name in files:
            if name in lock_files:
                target_path = os.path.join(root, name)
                try:
                    # 파일 존재 여부 재확인 후 삭제
                    if os.path.exists(target_path):
                        os.remove(target_path)
                        print(f"     [삭제] 잠금 파일 제거됨: {name}")
                except Exception as e:
                    print(f"     [주의] 잠금 파일({name}) 삭제 실패 (사용 중일 수 있음): {e}")

def clear_chrome_cache(user_data_dir):
    """
    지정된 Chrome 프로필 디렉토리에서 캐시 관련 폴더만 삭제합니다.
    (쿠키 및 세션 정보는 유지하여 로그인이 풀리지 않게 함)
    """
    import shutil
    if not os.path.exists(user_data_dir):
        return
        
    # 삭제할 캐시 관련 하위 폴더 목록
    # Default 폴더 내의 캐시들도 포함
    cache_dirs = [
        'Cache', 'Code Cache', 'GPUCache', 'ShaderCache',
        os.path.join('Default', 'Cache'),
        os.path.join('Default', 'Code Cache'),
        os.path.join('Default', 'GPUCache'),
        os.path.join('Default', 'Service Worker', 'CacheStorage'),
        os.path.join('Default', 'Service Worker', 'ScriptCache'),
    ]
    
    print(f"     [정리] Chrome 임시 캐시 정보를 삭제합니다...")
    for sub_dir in cache_dirs:
        target = os.path.join(user_data_dir, sub_dir)
        if os.path.exists(target):
            try:
                shutil.rmtree(target)
            except Exception:
                pass # 사용 중인 파일 등은 건너뜀

def setup_edge_driver(headless=True, use_profile=True):
    """
    Edge 브라우저 구동을 위한 공통 드라이버 설정 함수.
    """
    options = EdgeOptions()
    if headless:
        options.add_argument('--headless')
    
    if use_profile:
        # Edge 사용자 프로필 경로 설정
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            user_data_dir = os.path.join(base_dir, 'edge_profile')
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument("--profile-directory=Default")
        except Exception as e:
            print(f"     [주의] 프로필 경로 설정 중 오류: {e}")

    options.add_argument('--window-size=1024,768')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationTargetPrediction,SidePanelPinning,UserBypassUI')
    
    # 자동화 탐지 방지
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    options.add_argument(f'user-agent={ua}')
    
    try:
        driver = webdriver.Edge(options=options)
        return driver, "SUCCESS" if use_profile else "TEMP_PROFILE"
    except WebDriverException as e:
        err_msg = str(e).lower()
        if any(kw in err_msg for kw in ["in use", "user data", "session", "exited"]) and use_profile:
            print("     [정보] Edge 프로필 이슈로 프로필 없이 재시도합니다...")
            return setup_edge_driver(headless=headless, use_profile=False)
        else:
            print(f"     [오류] Edge 드라이버 구동 실패: {e}")
            return None, "FAILED"

def kill_chrome_processes():
    """기존에 남아있는 Chrome 및 ChromeDriver 프로세스를 강제로 종료합니다."""
    if sys.platform != 'win32':
        # 리눅스 환경에서는 pkill 사용 (없으면 무시)
        try:
            subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
            subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
        except: pass
        return

    try:
        # /F : 강제 종료, /T : 하위 프로세스 포함, /IM : 이미지 이름
        subprocess.run(['taskkill', '/F', '/T', '/IM', 'chrome.exe'], capture_output=True)
        subprocess.run(['taskkill', '/F', '/T', '/IM', 'chromedriver.exe'], capture_output=True)
        time.sleep(1) # 프로세스 정리 후 잠시 대기
    except:
        pass

def capture_screenshot(driver):
    """현재 브라우저 화면을 PNG 바이트 데이터로 캡처하여 반환합니다."""
    try:
        if driver:
            # get_screenshot_as_png()는 바이트 데이터를 반환하며, 
            # Streamlit의 st.image()에서 가장 안정적으로 지원됩니다.
            return driver.get_screenshot_as_png()
    except:
        pass
    return None
