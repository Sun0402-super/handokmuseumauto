import sys
import os

# 현재 디렉토리를 경로에 추가하여 driver_utils를 임포트할 수 있게 함
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from driver_utils import setup_chrome_driver, kill_chrome_processes
import time

def test_full_setup():
    print("기존 크롬 프로세스 정리 중...")
    kill_chrome_processes()
    
    print("driver_utils.setup_chrome_driver() 호출 중 (프로필 사용)...")
    try:
        driver, status = setup_chrome_driver(headless=False, use_profile=True)
        if driver:
            print(f"드라이버 시작 성공! 상태: {status}")
            print(f"브라우저 버전: {driver.capabilities['browserVersion']}")
            time.sleep(5)
            driver.get("https://www.google.com")
            print(f"페이지 로드 성공: {driver.title}")
            driver.quit()
            print("테스트 종료")
        else:
            print(f"드라이버 시작 실패. 상태: {status}")
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    test_full_setup()
