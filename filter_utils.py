import re
from datetime import datetime, timedelta

def parse_date_to_string(date_str):
    """
    상대적인 날짜(예: '2일 전', '1주 전')나 다양한 날짜 형식을 
    'yyyy-mm-dd' 절대 날짜 문자열로 변환합니다.
    """
    if not date_str or date_str == "-":
        return datetime.now().strftime("%Y-%m-%d")
        
    date_str = date_str.strip()
    now = datetime.now()
    
    try:
        # 1. '시간 전', '분 전', '방금' 등 -> 오늘
        if any(x in date_str for x in ["시간", "분", "방금", "초"]):
            return now.strftime("%Y-%m-%d")
            
        # 2. '일 전'
        if "일 전" in date_str:
            days = int(re.search(r"(\d+)", date_str).group(1))
            target_date = now - timedelta(days=days)
            return target_date.strftime("%Y-%m-%d")
                
        # 3. '주 전'
        if "주 전" in date_str:
            weeks = int(re.search(r"(\d+)", date_str).group(1))
            target_date = now - timedelta(weeks=weeks)
            return target_date.strftime("%Y-%m-%d")

        # 4. '달 전', '년 전'
        if "달 전" in date_str:
            months = int(re.search(r"(\d+)", date_str).group(1))
            target_date = now - timedelta(days=months * 30)
            return target_date.strftime("%Y-%m-%d")
        
        if "년 전" in date_str:
            years = int(re.search(r"(\d+)", date_str).group(1))
            target_date = now - timedelta(days=years * 365)
            return target_date.strftime("%Y-%m-%d")

        # 5. 절대 날짜 형식 (예: 2024.03.15, 03-15)
        nums = re.findall(r"\d+", date_str)
        if len(nums) >= 2:
            if len(nums) == 2: # 03.25 형식
                post_date = datetime(now.year, int(nums[0]), int(nums[1]))
            else: # 2024.03.15 형식
                year = int(nums[0])
                if year < 100: year += 2000 # 24 -> 2024
                post_date = datetime(year, int(nums[1]), int(nums[2]))
            return post_date.strftime("%Y-%m-%d")
    except:
        pass
        
    return date_str # 변환 실패 시 원본 반환

def is_relevant_by_keywords(text, title=""):
    """
    제목과 본문의 키워드를 기반으로 한독의약박물관 관련성 초동 필터링
    """
    if not text and not title:
        return False, "내용 없음"

    combined_text = (title + " " + text).lower()
    
    # 1. 필수 포함 키워드 (Inclusion) - 검색어 자체가 '한독의약박물관'이므로 기준 완화
    inclusion_keywords = [
        "한독의약박물관", "의약박물관", "한독박물관", "음성 박물관", 
        "서울관", "청담동 박물관", "한독 본사", "한독본사", "의약 유물",
        "한독", "박물관", "뮤지엄", "전시", "관람"
    ]
    
    found_inclusion = any(kw in combined_text for kw in inclusion_keywords)
    
    # 2. 제외 키워드 (Exclusion) - 광고, 홍보, 부동산, 유해물, 무관한 정보
    exclusion_keywords = [
        "보도자료", "뉴스", "특집기사", "학술대회", "신약", "떡박물관", 
        "등대박물관", "애니메이션박물관", "만화박물관", "화폐박물관",
        "부동산", "분양", "상가", "매물", "투자", "경매", "공인중개사",
        "맛집", "카페", "펜션", "숙소", "호텔", "모텔", "음악박물관",
        "유해", "도박", "성인", "광고", "마케팅"
    ]
    
    found_exclusion = any(kw in combined_text for kw in exclusion_keywords)
    
    # 3. 특정 패턴 필터링 (사용자 요청: 인근, 비슷)
    # '한독의약박물관 인근', '한독의약박물관 비슷' 등이 독립적으로 쓰이면 맛집/주변지 홍보일 가능성이 큼
    if re.search(r"한독의약박물관\s*(인근|근처|비슷|주변)", combined_text):
        # 만약 본문이 짧거나, 박물관 내부 시설에 대한 언급이 없으면 제외
        internal_keywords = ["전시", "유물", "관람", "체험", "프로그램", "독립운동가", "의약분업"]
        if not any(ikw in combined_text for ikw in internal_keywords):
            return False, "주변 정보 및 단순 비교 글 (박물관 후기 아님)"
    
    # 2. 제외 키워드 (Exclusion)
    # A. 강력한 제외 키워드 (광고, 부동산, 성인 등 - 무조건 제외에 가까움)
    strong_exclusion = [
        "부동산", "분양", "매물", "상가", "투자", "경매", "공인중개사",
        "아파트", "청약", "재건축", "재개발", "시세", "주상복합",
        "매매", "전세", "월세", "임대", "오피스텔", "빌라",
        "보도자료", "뉴스", "특집기사", "학술대회", "신약",
        "유해", "도박", "성인", "광고", "마케팅"
    ]
    
    # B. 약한 제외 키워드 (주변 맛집, 카페, 특정 지명 등 - 박물관 내용이 없으면 제외)
    weak_exclusion = ["맛집", "카페", "펜션", "숙소", "호텔", "모텔", "마곡"]
    
    # C. 박물관 핵심 키워드 (이게 있으면 맛집 글이라도 박물관 후기일 확률 높음)
    museum_core = ["전시", "유물", "관람", "체험", "프로그램", "독립운동가", "의약분업", "도슨트"]

    # 로직 시작
    if any(sq in combined_text for sq in strong_exclusion):
        # 강력 제외 키워드가 있더라도 제목에 '박물관'이 있으면 수동 확인을 위해 일단 포함할 수도 있으나, 
        # 광고성이 짙으므로 여기서는 제외를 기본으로 함
        return False, f"강력 제외 키워드 검출 ({[kw for kw in strong_exclusion if kw in combined_text][0]})"

    # 특정 패턴 필터링 (사용자 요청: 인근, 비슷)
    has_nearby_pattern = re.search(r"한독의약박물관\s*(인근|근처|비슷|주변)", combined_text)
    has_weak_exclusion = any(wq in combined_text for wq in weak_exclusion)
    has_museum_core = any(mc in combined_text for mc in museum_core)
    
    # [수정] 제목에 박물관 이름이 명확히 포함된 경우 관련성 가점
    is_title_strong = "한독의약박물관" in title or "의약박물관" in title

    if has_nearby_pattern or has_weak_exclusion:
        # 제목이 강력하고 박물관 핵심 키워드가 하나라도 있으면 통과
        if is_title_strong and (has_museum_core or "박물관" in text[:100]):
            return True, "키워드 통과 (제목 기반 핵심 내용 확인)"
            
        # 주변 정보나 맛집 키워드가 있지만, 박물관 핵심 내용(전시 등)이 언급되었다면 통과
        if has_museum_core:
            return True, "키워드 통과 (박물관 내용 포함)"
            
        # 제목이나 본문 앞부분에 박물관 내용이 명확하지 않으면 제외
        if "박물관" not in title and "박물관" not in text[:100]:
            return False, "주변 정보/광고성 글 (박물관 핵심 내용 미검출)"

    # 기본 관련성 체크
    if is_title_strong or "한독" in combined_text or "박물관" in combined_text or found_inclusion:
        return True, "키워드 통과"

    return False, "박물관 관련 키워드 미검출"

def is_within_one_week(date_str):
    """
    네이버/구글 등의 날짜 텍스트를 분석하여 7일 이내인지 판별
    예: '21시간 전', '2일 전', '1주 전', '2024.03.15'
    """
    if not date_str:
        return True # 날짜가 없으면 일단 포함 (안정성)
    
    date_str = date_str.strip()
    
    # 1. '시간 전', '분 전', '방금' 등은 무조건 오늘/어제
    if "시간" in date_str or "분" in date_str or "방금" in date_str or "초" in date_str:
        return True
    
    # 2. '일 전' 처리
    if "일 전" in date_str:
        try:
            days = int(re.search(r"(\d+)", date_str).group(1))
            return days <= 7
        except:
            return True
            
    # 3. '주 전' 처리
    if "주 전" in date_str:
        try:
            weeks = int(re.search(r"(\d+)", date_str).group(1))
            return weeks <= 1 # '1주 전'까지 인정
        except:
            return True

    # 4. '달 전', '년 전' 처리
    if "달 전" in date_str or "년 전" in date_str:
        return False

    # 5. 절대 날짜 형식 (예: 2024.03.15, 2024-03-15)
    try:
        # 숫자만 추출
        nums = re.findall(r"\d+", date_str)
        if len(nums) >= 2:
            from datetime import datetime
            now = datetime.now()
            # 연도가 없으면 올해로 가정
            if len(nums) == 2:
                post_date = datetime(now.year, int(nums[0]), int(nums[1]))
            else:
                post_date = datetime(int(nums[0]), int(nums[1]), int(nums[2]))
            
            delta = now - post_date
            return delta.days <= 7
    except:
        pass

    return True # 판단 불가 시 포함
