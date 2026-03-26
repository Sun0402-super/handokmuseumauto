import os
import time
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager

def test_edge_setup():
    print("Edge 드라이버 초기화 테스트 시작...")
    options = Options()
    
    # 사용자 데이터 경로 설정
    user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
    print(f"사용자 데이터 경로: {user_data_dir}")
    
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument("profile-directory=Default")
    options.add_argument("--start-maximized")
    
    try:
        service = Service(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)
        
        print("Edge 브라우저 접속 중 (Instagram)...")
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        print(f"현재 URL: {driver.current_url}")
        print(f"페이지 타이틀: {driver.title}")
        
        driver.quit()
        print("테스트 성공: Edge 드라이버가 정상적으로 초기화되었습니다.")
    except Exception as e:
        print(f"테스트 실패: {e}")

if __name__ == "__main__":
    test_edge_setup()
