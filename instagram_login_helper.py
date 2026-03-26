import time
import os
import sys
from driver_utils import setup_chrome_driver, kill_chrome_processes

# UTF-8 출력 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def instagram_manual_login():
    """
    사용자가 직접 인스타그램에 로그인하여 세션을 브라우저 프로필에 저장할 수 있도록 
    브라우저를 열어줍니다.
    """
    kill_chrome_processes()
    print("\n" + "="*60)
    print(" [인스타그램 자동 로그인 세션 만들기]")
    print("="*60)
    print(" 1. 곧 브라우저 창이 열립니다.")
    print(" 2. 인스타그램 사이트에서 직접 로그인을 완료해주세요.")
    print(" 3. '정보 저장' 여부를 묻는다면 반드시 '정보 저장'을 클릭하세요.")
    print(" 4. 로그인이 완료된 후, 이 창(터미널)으로 돌아와 엔터를 치시면 종료됩니다.")
    print("="*60 + "\n")

    driver, status = setup_chrome_driver(headless=False, use_profile=True)
    if not driver:
        print("❌ 브라우저를 구동하지 못했습니다.")
        return

    try:
        driver.get("https://www.instagram.com/accounts/login/")
        input("\n>>> 로그인을 완료하고 세션을 저장하셨다면 엔터(Enter)를 눌러주세요...")
        print("\n✅ 세션이 저장되었습니다. 이제 자동 수집 시 로그인이 유지됩니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    instagram_manual_login()
