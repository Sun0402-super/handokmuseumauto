import os

# Gemini API 관련
DEFAULT_API_KEY = "AIzaSyDLD7stdtusDTxCYrqonQiL4S5m050X98s"

# KcBERT 모델 로드 (전역 변수로 관리하여 중복 로드 방지)
SENTIMENT_PIPELINE = None

# 사용자 정의 긍정 키워드 (네이버/구글/기타)
POSITIVE_KEYWORDS = [
    "좋다", "추천", "재방문", "유익", "친절", "주차장 넓음", "재미", "가치", "또 올 의사", 
    "미래 약사", "미래 의사", "시설 편리", "편익", "올만 하다", "주변 추천", "지인 추천",
    "즐겁다", "만족", "최고", "훌륭", "좋았", "좋군", "좋네", "좋더라", "좋아", "즐거", "즐겼",
    "감사", "고맙", "이쁘", "예쁘", "유용", "잘되", "가볼만", "좋은"
]

# 인스타그램 전용 긍정 해시태그
INSTA_POSITIVE_HASHTAGS = [
    "#아이와가볼만한곳", "#주말교육", "#주말체험", "#프로그램", "#교육", 
    "#박물관체험", "#아이와주말", "#한독의약박물관"
]

# 사용자 정의 부정 키워드
NEGATIVE_KEYWORDS = [
    "불친절", "실망", "별로", "좁다", "비싸다", "아쉽다", "주차 불편", "전시 빈약", 
    "설명 부족", "볼게 없음", "돈아깝", "노잼", "비추", "다시는 안 가", "다신 안 가"
]

def check_forced_sentiment(text, is_instagram=False):
    """
    텍스트 내에 특정 긍정/부정 키워드가 포함되어 있는지 확인합니다.
    사용자 가이드에 따라 AI 분석 전 우선 순위를 갖습니다.
    """
    if not text: return None
    
    # 1. 인스타그램 전용 긍정 해시태그 체크
    if is_instagram:
        for tag in INSTA_POSITIVE_HASHTAGS:
            if tag in text:
                return ("긍정", f"인스타그램 긍정 해시태그({tag}) 감지")
                
    # 2. 일반 긍정 키워드 체크
    for kw in POSITIVE_KEYWORDS:
        if kw in text:
            return ("긍정", f"긍정 키워드('{kw}') 포함")
            
    # 3. 일반 부정 키워드 체크 (사용자 추가 요청)
    for kw in NEGATIVE_KEYWORDS:
        if kw in text:
            return ("부정", f"부정 키워드('{kw}') 감지")
            
    return None

def analyze_sentiment_kcbert(text):
    global SENTIMENT_PIPELINE
    if not text or not text.strip():
        return ("분석불가", "본문 내용 없음")
    
    try:
        if SENTIMENT_PIPELINE is None:
            try:
                from transformers import pipeline
            except ImportError:
                return ("분석불가", "로컬 분석 라이브러리(transformers)가 설치되지 않았습니다. Gemini 모드를 사용하세요.")
            
            # NSMC로 파인튜닝된 KcBERT 모델 사용
            SENTIMENT_PIPELINE = pipeline(
                "text-classification", 
                model="jaehyeong/kcbert-base-finetuned-nsmc",
                device=-1 # CPU 사용
            )
        
        clean_text = text[:510]
        result = SENTIMENT_PIPELINE(clean_text)[0]
        label = result['label']
        score = result['score']
        
        if label == '1' or label == 'LABEL_1':
            sentiment = "긍정"
            reason = f"KcBERT 분석 결과 긍정 확률 {score:.1%}"
        elif label == '0' or label == 'LABEL_0':
            sentiment = "부정"
            reason = f"KcBERT 분석 결과 부정 확률 {score:.1%}"
        else:
            sentiment = "중립"
            reason = f"분석 결과 모호함 ({label})"
            
        return (sentiment, reason)
    except Exception as e:
        return ("분석불가", f"오류: {str(e)[:50]}")

def analyze_sentiment_gemini(text, api_key, use_summary=True):
    if not text or not text.strip():
        return ("분석불가", "본문 내용 없음")
    
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        # 프롬프트 강화: 관련성 체크 추가 (한독의약박물관 음성/서울관 모두 포함)
        prompt = f"""아래는 수집된 게시물(블로그, 리뷰, SNS) 내용입니다.
이 후기가 '한독의약박물관(충북 음성 소재)' 또는 '한독의약박물관 서울관(강남구 청담동 소재)'과 관련된 내용인지 먼저 판단하세요.

만약 해당 박물관과 무관한 뉴스 기사, 보도자료, 혹은 다른 장소(예: 떡박물관 등)에 대한 글이라면 감성을 '부적합'으로 분류하세요.

박물관과 관련된 후기라면, 아래 기준에 따라 '긍정', '중립', '부정' 중 하나로 분류하세요.
- 재미있다, 좋다, 만족, 추천, 유익, 즐겁다, 감사하다, 예쁘다, 가볼만하다 등의 표현이 있거나,
- 직원이 친절함, 시설이 깨끗함/쾌적함, 주차가 편리함, 전시가 체계적임 등의 긍정적 측면이 서술되었다면 적극적으로 '긍정'으로 분류하세요.
- 특히 박물관 내 **카페나 공원(산책로) 시설이 좋았다**는 언급, 혹은 **박물관과 관련된 체험 프로그램(예: 토크콘서트 등)이 즐거웠다**는 내용은 매우 긍정적인 후기입니다.
- 과거의 편견(지루할 줄 알았는데 아니었다 등)을 언급하며 **반전된 긍정적 감정**을 표현한 경우에도 '긍정'으로 분류해야 합니다.
- 반대로 서비스 불만족, 시설 낙후, 볼거리 부족 등의 내용이 있다면 '부정'으로 분류하세요.
- 단순 정보 전달이거나 긍정도 부정도 아닌 평이한 내용은 '중립'으로 분류하세요.

반드시 다음 형식을 지켜 답변하세요:
1. 관련성: [적합 / 부적합]
2. 감성: [긍정 / 중립 / 부정 / 부적합]
"""
        if use_summary:
            prompt += "\n3. 내용 요약: [반복되는 주요 단어들을 앞에 나열한 뒤, 가장 중요한 핵심 내용을 한 줄로 요약해 주세요. 예: 키워드, 단어, 단어 | 핵심 요약 내용]"
        else:
            prompt += "\n3. 내용 요약: [요약 생략]"

        prompt += f"\n\n--- 게시물 본문 ---\n{text[:2000]}\n"
        
        response = client.models.generate_content(model="gemini-2.0-flash-lite-preview-02-05", contents=prompt)
        res_text = response.text.strip()
        
        sentiment = "중립"
        reason = ""
        
        # 더 유연한 파싱 로직
        import re
        
        # 1. 감성 및 관련성 추출
        # 관련성 체크
        relevance = "적합"
        rel_match = re.search(r"관련성[:\s]+(적합|부합|부적합|irrelevant|relevant)", res_text, re.I)
        if rel_match:
            if "부적합" in rel_match.group(1) or "irrelevant" in rel_match.group(1).lower():
                relevance = "부적합"
        
        # 감성 추출
        s_match = re.search(r"감성[:\s]+(긍정|부정|중립|부적합|Positive|Negative|Neutral|Irrelevant)", res_text, re.I)
        if s_match:
            raw_sentiment = s_match.group(1).strip().lower()
            if "부적합" in raw_sentiment or "irrelevant" in raw_sentiment: sentiment = "부적합"
            elif "긍정" in raw_sentiment or "positive" in raw_sentiment: sentiment = "긍정"
            elif "부정" in raw_sentiment or "negative" in raw_sentiment: sentiment = "부정"
            else: sentiment = "중립"
        
        # 관련성이 부적합이면 감성도 부적합으로 강제 설정
        if relevance == "부적합":
            sentiment = "부적합"
        
        # 2. 내용 요약/이유 추출
        # (내용 요약|이유|요약|Summary) 뒤에 오는 텍스트를 찾되, 다른 필드(감성 등)가 나오기 전까지 끊음
        r_patterns = [r"(?:내용 요약|이유|요약|Summary)[:\s]+(.*?)(?=\n(?:감성|Sentiment)|$)", r"(?:내용 요약|이유|요약|Summary)[:\s]+(.*)"]
        for pat in r_patterns:
            r_match = re.search(pat, res_text, re.DOTALL | re.I)
            if r_match:
                reason = r_match.group(1).strip()
                if reason: break
        
        # 폴백: 특정 키워드가 없는 경우 전체 텍스트에서 불필요한 부분 제거 후 사용
        if not reason:
            reason = res_text.replace(f"감성: {sentiment}", "").strip()
            # 줄바꿈이나 번호 등 정리
            reason = re.sub(r"^\d+\.\s*", "", reason) 
            reason = re.sub(r"[*#]", "", reason).strip()

        # 분석 결과 가공
        reason = reason.replace("\n", " ").strip()
        if len(reason) > 300:
            reason = reason[:297] + "..."
            
        return (sentiment, reason)
    except Exception as e:
        return ("분석불가", f"Gemini 오류: {str(e)[:100]}")

def analyze_sentiment(text, api_key=None, mode="gemini", is_instagram=False, use_summary=True, rating=None):
    """모드에 따라 감성 분석 수행 (기본은 gemini)"""
    
    # -1. 별점 체크 (별점 5점이면 무조건 긍정으로 분류 - 사용자 요청)
    if rating == "5" or rating == 5:
        return ("긍정", "별점 5점 만점 (자동 분류)")
    
    # 0. 우선 순위 키워드 체크 (사용자 요청 반영: 긍정/부정 우선 판정)
    forced_res = check_forced_sentiment(text, is_instagram=is_instagram)
    if forced_res:
        return forced_res
        
    if mode == "kcbert":
        # KcBERT 시도
        return analyze_sentiment_kcbert(text)
    else:
        return analyze_sentiment_gemini(text, api_key or DEFAULT_API_KEY, use_summary=use_summary)
