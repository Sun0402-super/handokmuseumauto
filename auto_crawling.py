import os
import sys
import datetime
import pandas as pd
import time
import re

from driver_utils import setup_chrome_driver, clear_chrome_cache, kill_chrome_processes
from naver_blog_crawling import crawl_naver_blog
from daum_crawling import crawl_daum
from kakao_map_crawling import crawl_kakao_map
from google_map_crawling import run_google_maps_crawler
from instagram_crawling import instagram_login, crawl_hashtag, crawl_location
from sentiment_utils import DEFAULT_API_KEY
from filter_utils import is_relevant_by_keywords, parse_date_to_string, is_within_one_week

def main():
    # 수집 시작 전 기존 크롬 프로세스 정리 (충돌 방지)
    kill_chrome_processes()
    
    print("="*50)
    print(f"[자동 수집 시작] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # 설정값
    api_key = DEFAULT_API_KEY
    use_sentiment = True
    navers_max_pages = 5
    insta_max_posts = 50
    
    all_results = []
    
    # 1. 네이버 블로그 크롤링
    print("\n[단계 1] 네이버 블로그 수집 중...")
    try:
        naver_count = 0
        for item in crawl_naver_blog("한독의약박물관", navers_max_pages, api_key, use_sentiment):
            if isinstance(item, dict):
                item['출처'] = '네이버 블로그'
                all_results.append(item)
                naver_count += 1
        print(f"     ✅ 네이버 블로그 {naver_count}건 수집 완료")
    except Exception as e:
        print(f"❌ 네이버 수집 중 오류: {e}")

    # 2. 다음 검색 크롤링
    print("\n[단계 2] Daum 검색 수집 중...")
    try:
        daum_count = 0
        for item in crawl_daum("한독의약박물관", 1, api_key, use_sentiment):
            if isinstance(item, dict):
                is_rel, reason = is_relevant_by_keywords(item.get('본문내용', ''), item.get('제목', ''))
                if is_rel:
                    item['출처'] = 'Daum 검색'
                    all_results.append(item)
                    daum_count += 1
        print(f"     ✅ Daum 검색 {daum_count}건 수집 완료")
    except Exception as e:
        print(f"❌ Daum 수집 중 오류: {e}")

    # 3. 카카오맵 리뷰 크롤링
    print("\n[단계 3] 카카오맵 리뷰 수집 중...")
    try:
        kakao_count = 0
        for item in crawl_kakao_map(api_key, use_sentiment):
            if isinstance(item, dict):
                item['출처'] = '카카오맵 리뷰'
                all_results.append(item)
                kakao_count += 1
        print(f"     ✅ 카카오맵 리뷰 {kakao_count}건 수집 완료")
    except Exception as e:
        print(f"❌ 카카오맵 수집 중 오류: {e}")

    # 4. 구글 리뷰 크롤링
    print("\n[단계 4] 구글 리뷰 수집 중...")
    try:
        google_count = 0
        for item in run_google_maps_crawler(api_key, use_sentiment):
            if isinstance(item, dict):
                item['출처'] = '구글 리뷰'
                all_results.append(item)
                google_count += 1
        print(f"     ✅ 구글 리뷰 {google_count}건 수집 완료")
    except Exception as e:
        print(f"❌ 구글 리뷰 수집 중 오류: {e}")

    # 5. 인스타그램 크롤링
    print("\n[단계 5] 인스타그램 수집 중...")
    try:
        driver, status = setup_chrome_driver(headless=True, use_profile=True)
        if driver and instagram_login(driver, "", ""):
            results = crawl_location(driver, "109120676658159", max_posts=insta_max_posts, api_key=api_key, use_sentiment=use_sentiment)
            for r in results:
                r['출처'] = '인스타그램'
                all_results.append(r)
            print(f"     ✅ 인스타그램 {len(results)}건 수집 완료")
            driver.quit()
        else:
            print("     ⚠️ 인스타그램 로그인을 건너뜁니다.")
            if driver: driver.quit()
    except Exception as e:
        print(f"❌ 인스타그램 수집 중 오류: {e}")

    # 데이터 필터링 (최근 1주일 이내 & 관련성 체크 & 중복 제거)
    print("\n[단계 6] 데이터 필터링 중 (날짜, 관련성, 중복 제거)...")
    
    # 1. 기본 필터링 (날짜 & 관련성)
    pre_filtered = []
    for item in all_results:
        date_str = item.get('작성일', '')
        title = item.get('제목', '')
        content = item.get('본문내용', '')
        
        if not is_within_one_week(date_str):
            continue
            
        is_rel, reason = is_relevant_by_keywords(content, title)
        if not is_rel:
            continue
            
        pre_filtered.append(item)
    
    # 2. 중복 제거 (내용 기준, '네이버 블로그' 우선)
    # 내용(본문내용)을 키워드로 하여 그룹화 후 우선순위 적용
    dedup_dict = {}
    for item in pre_filtered:
        content_key = re.sub(r'\s+', '', item.get('본문내용', '')).strip() # 공백 제거 후 비교
        if not content_key:
            continue
            
        if content_key not in dedup_dict:
            dedup_dict[content_key] = item
        else:
            # 기존에 저장된 것보다 '네이버 블로그'가 우선순위가 높음
            existing_src = dedup_dict[content_key].get('출처', '')
            current_src = item.get('출처', '')
            
            if existing_src != '네이버 블로그' and current_src == '네이버 블로그':
                dedup_dict[content_key] = item
    
    filtered_results = list(dedup_dict.values())
    removed_count = len(all_results) - len(filtered_results)
    all_results = filtered_results
    if removed_count > 0:
        print(f"     ⚠️ {removed_count}건의 오래된 후기가 제외되었습니다.")
    print(f"     ✅ 총 {len(all_results)}건의 최신 후기 유지")

    # 결과 저장
    if not all_results:
        print("\n[결과] 수집된 데이터가 없어 종료합니다.")
        return

    print("\n[단계 7] 엑셀 파일 저장 중...")
    now_date = datetime.datetime.now().strftime("%Y%m%d")
    BASE_RESULT_DIR = r"C:\Users\kr2200047\OneDrive - handokinc\J_ 한독의약박물관 - 문서\한독의약박물관 관람 후기"
    RESULT_DIR = os.path.join(BASE_RESULT_DIR, f"[Data_{now_date}]")
    os.makedirs(RESULT_DIR, exist_ok=True)

    # 1. 플랫폼별 개별 파일 저장
    df = pd.DataFrame(all_results)
    platforms_mapping = {
        '네이버 블로그': {
            '출처': '플랫폼(출처)', '작성자': '블로그 작성자', '작성일': '작성일', '제목': '블로그 제목', 
            '본문내용': '본문 내용', '본문 키워드': '본문 키워드', '본문 한 줄 요약': '본문 한 줄 요약', 
            'URL': 'URL', '감성분석': '긍정/부정(감성분석)', '분석이유': '분석이유'
        },
        'Daum 검색': {
            '출처': '플랫폼(출처)', '작성자': '블로그 작성자', '작성일': '작성일', '제목': '블로그 제목', 
            '본문내용': '본문 내용', '본문 키워드': '본문 키워드', '본문 한 줄 요약': '본문 한 줄 요약', 
            'URL': 'URL', '감성분석': '긍정/부정(감성분석)', '분석이유': '분석이유'
        },
        '카카오맵 리뷰': {
            '출처': '플랫폼(출처)', '작성자': '작성자', '별점': '별점', '작성일': '작성일', 
            '본문내용': '본문 내용', '본문 키워드': '본문 키워드', '본문 한 줄 요약': '본문 한 줄 요약', 
            '감성분석': '긍정/부정(감성분석)', '분석이유': '분석이유'
        },
        '구글 리뷰': {
            '출처': '플랫폼(출처)', '작성자': '작성자', '별점': '별점', '작성일': '작성일', 
            '본문내용': '본문 내용', '본문 키워드': '본문 키워드', '본문 한 줄 요약': '본문 한 줄 요약', 
            '감성분석': '긍정/부정(감성분석)', '분석이유': '분석이유'
        },
        '인스타그램': {
            '출처': '플랫폼(출처)', '작성자': '계정', '작성일': '작성일', '본문내용': '본문 내용', 
            '해시태그': '해시태그', '본문 키워드': '키워드', 'URL': 'URL', '감성분석': '긍정/부정(감성분석)', '분석이유': '분석이유'
        }
    }

    for platform_name, col_mapping in platforms_mapping.items():
        pdf = df[df['출처'] == platform_name]
        if not pdf.empty:
            processed = []
            for _, row in pdf.iterrows():
                item = row.to_dict()
                reason = item.get('분석이유', '')
                keywords, summary = "", ""
                if "|" in reason:
                    parts = reason.split("|", 1)
                    keywords = parts[0].strip()
                    summary = parts[1].strip()
                item['본문 키워드'] = keywords
                item['본문 한 줄 요약'] = summary
                
                if platform_name == '인스타그램':
                    item['해시태그'] = ", ".join(re.findall(r'#(\w+)', item.get('본문내용', '')))
                
                new_item = {new_key: item.get(old_key, '') for old_key, new_key in col_mapping.items()}
                processed.append(new_item)
            
            p_df = pd.DataFrame(processed)
            p_filename = os.path.join(RESULT_DIR, f"{platform_name}_{now_date}.xlsx")
            p_df.to_excel(p_filename, index=False)
            print(f"      💾 {platform_name} 저장 완료")

    # 2. 통합 보고서 생성 (사용자 요청 양식)
    unified_data = []
    for i, (_, row) in enumerate(df.iterrows(), 1):
        item = row.to_dict()
        src = item.get('출처', '')
        reason = item.get('분석이유', '')
        keywords, summary = "", ""
        if "|" in reason:
            parts = reason.split("|", 1)
            keywords = parts[0].strip()
            summary = parts[1].strip()
        
        if src == '인스타그램':
            url_column = item.get('URL', '') # URL은 URL 컬럼으로
            # 인스타그램의 경우 작성자가 계정명인 경우가 많으므로 유지, 한줄 요약은 요약 정보로
            summary_column = summary if summary else ", ".join(re.findall(r'#(\w+)', item.get('본문내용', '')))
        else:
            url_column = item.get('URL', '')
            summary_column = summary

        unified_row = {
            "연번": i,
            "플랫폼": src,
            "작성일": item.get('작성일', '-'),
            "긍정/부정(감성분석)": item.get('감성분석', ''),
            "분석 이유": reason,
            "본문 키워드": keywords,
            "한줄 요약": summary_column,
            "URL": url_column
        }
        unified_data.append(unified_row)
    
    unified_df = pd.DataFrame(unified_data)
    cols = ["연번", "플랫폼", "작성일", "긍정/부정(감성분석)", "분석 이유", "본문 키워드", "한줄 요약", "URL"]
    unified_df = unified_df[cols]
    
    # 긍정 후기만 추출
    positive_df = unified_df[unified_df["긍정/부정(감성분석)"] == "긍정"].copy()
    positive_df["연번"] = range(1, len(positive_df) + 1) # 연번 재정렬
    
    unified_filename = os.path.join(RESULT_DIR, f"{now_date}_한독의약박물관 관람 후기.xlsx")
    
    # 여러 시트로 저장
    with pd.ExcelWriter(unified_filename, engine='openpyxl') as writer:
        unified_df.to_excel(writer, sheet_name='전체 후기', index=False)
        positive_df.to_excel(writer, sheet_name='긍정 후기', index=False)
        
    print(f"📊 통합 보고서 생성 완료 (시트: 전체 후기, 긍정 후기): {unified_filename}")

    print("\n" + "="*50)
    print(f"[자동 수집 완료] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

if __name__ == "__main__":
    main()
