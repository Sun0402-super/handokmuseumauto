import re
from datetime import datetime, timedelta

def parse_date_to_string(date_str):
    """
    상대적인 날짜(예: '2일 전', '1주 전', '2 months ago')나 다양한 날짜 형식을
    'YYYY-MM-DD' 절대 날짜 문자열로 변환합니다.
    구글 지도는 한국어/영어 혼용으로 날짜를 반환할 수 있어 두 형식 모두 지원합니다.
    """
    if not date_str or date_str == "-":
        return datetime.now().strftime("%Y-%m-%d")

    date_str = date_str.strip()
    now = datetime.now()

    try:
        # ── 한국어 형식 ──────────────────────────────────────────────────
        # 1. '시간 전', '분 전', '방금', '초 전' → 오늘
        if any(x in date_str for x in ["시간", "분", "방금", "초"]):
            return now.strftime("%Y-%m-%d")

        # 2. '일 전'
        if "일 전" in date_str:
            days = int(re.search(r"(\d+)", date_str).group(1))
            return (now - timedelta(days=days)).strftime("%Y-%m-%d")

        # 3. '주 전'
        if "주 전" in date_str:
            weeks = int(re.search(r"(\d+)", date_str).group(1))
            return (now - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

        # 4. '달 전' / '개월 전'
        if "달 전" in date_str or "개월 전" in date_str:
            months = int(re.search(r"(\d+)", date_str).group(1))
            return (now - timedelta(days=months * 30)).strftime("%Y-%m-%d")

        # 5. '년 전'
        if "년 전" in date_str:
            years = int(re.search(r"(\d+)", date_str).group(1))
            return (now - timedelta(days=years * 365)).strftime("%Y-%m-%d")

        # ── 영어 형식 (구글 지도 영어 로케일 대응) ─────────────────────
        ds_lower = date_str.lower()

        # 'a minute ago', 'an hour ago', 'just now' → 오늘
        if any(x in ds_lower for x in ["minute", "hour", "just now", "second"]):
            return now.strftime("%Y-%m-%d")

        # 'X day(s) ago'
        m = re.search(r"(\d+)\s*day", ds_lower)
        if m:
            return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
        if "a day ago" in ds_lower:
            return (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # 'X week(s) ago'
        m = re.search(r"(\d+)\s*week", ds_lower)
        if m:
            return (now - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d")
        if "a week ago" in ds_lower:
            return (now - timedelta(weeks=1)).strftime("%Y-%m-%d")

        # 'X month(s) ago'
        m = re.search(r"(\d+)\s*month", ds_lower)
        if m:
            return (now - timedelta(days=int(m.group(1)) * 30)).strftime("%Y-%m-%d")
        if "a month ago" in ds_lower:
            return (now - timedelta(days=30)).strftime("%Y-%m-%d")

        # 'X year(s) ago'
        m = re.search(r"(\d+)\s*year", ds_lower)
        if m:
            return (now - timedelta(days=int(m.group(1)) * 365)).strftime("%Y-%m-%d")
        if "a year ago" in ds_lower:
            return (now - timedelta(days=365)).strftime("%Y-%m-%d")

        # ── 절대 날짜 형식 (예: 2024.03.15 / 2024-03-15 / 03.25) ─────
        nums = re.findall(r"\d+", date_str)
        if len(nums) >= 2:
            if len(nums) == 2:  # 03.25 형식
                post_date = datetime(now.year, int(nums[0]), int(nums[1]))
            else:               # 2024.03.15 형식
                year = int(nums[0])
                if year < 100:
                    year += 2000
                post_date = datetime(year, int(nums[1]), int(nums[2]))
            return post_date.strftime("%Y-%m-%d")
    except:
        pass

    return date_str  # 변환 실패 시 원본 반환

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
    # [수정] 제목에 박물관 이름이 명시된 경우 관련성이 매우 높으므로 가중치 부여
    is_title_strong = "한독의약박물관" in title or "의약박물관" in title
    
    # 강력 제외 키워드 검사 (단, 제목이 강력하면 '뉴스', '보도자료'는 허용)
    for sq in strong_exclusion:
        if sq in combined_text:
            # 제목에 박물관 이름이 있으면 뉴스/보도자료 관련 키워드는 무시하고 통과 시킴
            if is_title_strong and sq in ["뉴스", "보도자료", "특집기사", "학술대회"]:
                continue
            return False, f"강력 제외 키워드 검출 ({sq})"

    # 특정 패턴 필터링 (사용자 요청: 인근, 비슷)
    has_nearby_pattern = re.search(r"한독의약박물관\s*(인근|근처|비슷|주변)", combined_text)
    has_weak_exclusion = any(wq in combined_text for wq in weak_exclusion)
    has_museum_core = any(mc in combined_text for mc in museum_core)
    
    if has_nearby_pattern or has_weak_exclusion:
        # 제목이 강력하고 박물관 핵심 키워드나 내용이 확인되면 통과
        if is_title_strong and (has_museum_core or "박물관" in text[:150]):
            return True, "키워드 통과 (제목 기반 핵심 내용 확인)"
            
        # 주변 정보나 맛집 키워드가 있지만, 박물관 핵심 내용(전시 등)이 언급되었다면 통과
        if has_museum_core:
            return True, "키워드 통과 (박물관 내용 포함)"
            
        # 제목이나 본문 앞부분에 박물관 내용이 명확하지 않으면 제외
        if "박물관" not in title and "박물관" not in text[:150]:
            return False, "주변 정보/광고성 글 (박물관 핵심 내용 미검출)"

    # 기본 관련성 체크
    if is_title_strong or found_inclusion or "박물관" in combined_text:
        return True, "키워드 통과"

    return False, "박물관 관련 키워드 미검출"

def is_within_one_week(date_str):
    """
    날짜 텍스트를 분석하여 크롤링 시점 기준 7일 이내인지 판별.
    한국어(일 전/주 전/달 전) 및 영어(days ago/weeks ago/months ago) 모두 지원.
    7일 초과 시 False를 반환하며, 판단 불가 시 True(포함)로 처리.
    """
    if not date_str:
        return True

    date_str = date_str.strip()
    ds_lower = date_str.lower()

    # ── 한국어 패턴 ──────────────────────────────────────────────────────
    # 1. 시간/분/초/방금 → 당일 → 포함
    if any(x in date_str for x in ["시간", "분", "방금", "초"]):
        return True

    # 2. 'N일 전'
    if "일 전" in date_str:
        try:
            return int(re.search(r"(\d+)", date_str).group(1)) <= 7
        except:
            return True

    # 3. 'N주 전' — 1주(≤7일)만 허용
    if "주 전" in date_str:
        try:
            return int(re.search(r"(\d+)", date_str).group(1)) <= 1
        except:
            return True

    # 4. '달 전' / '개월 전' / '년 전' → 7일 초과 → 제외
    if any(x in date_str for x in ["달 전", "개월 전", "년 전"]):
        return False

    # ── 영어 패턴 (구글 지도 영어 로케일) ──────────────────────────────
    # 시간/분/초/just now → 포함
    if any(x in ds_lower for x in ["minute", "hour", "second", "just now"]):
        return True

    # 'X day(s) ago' / 'a day ago'
    m = re.search(r"(\d+)\s*day", ds_lower)
    if m:
        return int(m.group(1)) <= 7
    if "a day ago" in ds_lower:
        return True

    # 'X week(s) ago' / 'a week ago' → 1주만 허용
    m = re.search(r"(\d+)\s*week", ds_lower)
    if m:
        return int(m.group(1)) <= 1
    if "a week ago" in ds_lower:
        return True

    # 'X month(s) ago' / 'a month ago' / 'X year(s) ago' → 제외
    if any(x in ds_lower for x in ["month", "year"]):
        return False

    # ── 절대 날짜 (예: 2024.03.15 / 2024-03-15) ────────────────────────
    try:
        nums = re.findall(r"\d+", date_str)
        now = datetime.now()
        if len(nums) == 2:
            post_date = datetime(now.year, int(nums[0]), int(nums[1]))
        elif len(nums) >= 3:
            post_date = datetime(int(nums[0]), int(nums[1]), int(nums[2]))
        else:
            return True
        return (now - post_date).days <= 7
    except:
        pass

    return True  # 판단 불가 → 포함
