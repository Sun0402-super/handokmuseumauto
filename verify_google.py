from google_map_crawling import run_google_maps_crawler

def test_google_edge():
    print("구글 지도 Edge 크롤러 테스트 시작...")
    # api_key는 분석을 건너뛰기 위해 None으로 전달 (테스트 목적)
    crawler = run_google_maps_crawler(api_key=None, use_sentiment=False)
    
    for msg in crawler:
        if isinstance(msg, str):
            print(f"로그: {msg}")
        else:
            print(f"결과 발견: {msg.get('작성자')} - {msg.get('본문내용')[:30]}...")
            break # 첫 번째 결과만 확인

if __name__ == "__main__":
    test_google_edge()
