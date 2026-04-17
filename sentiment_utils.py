import os
import re
import time
from collections import Counter

# Gemini API 관련
DEFAULT_API_KEY = "AIzaSyDLD7stdtusDTxCYrqonQiL4S5m050X98s"

# 사용 가능한 Gemini 모델 (우선순위 순)
GEMINI_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
]

# 사용자 정의 긍정 키워드
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
    "불친절", "실망", "별로", "좁다", "아쉽다", "주차 불편", "전시 빈약",
    "설명 부족", "볼게 없음", "노잼", "비추", "다시는 안 가", "다신 안 가",
    "불편", "재미없다", "재미 없다", "재방문 의사 없음", "재방문 의사가 없", "다시 안 올", "또 오고 싶지 않"
]

# 키워드 추출 시 제외할 불용어
_STOPWORDS = {
    "이", "그", "저", "것", "수", "을", "를", "이", "가", "은", "는", "도", "에", "의", "와", "과",
    "하다", "있다", "없다", "이다", "하고", "하여", "하면", "했다", "했어", "했는데", "하는",
    "합니다", "해요", "이에", "이고", "한다", "있어", "없어", "그리고", "하지만", "그런데", "그래서",
    "너무", "정말", "진짜", "매우", "아주", "조금", "많이", "좀", "제", "우리", "저는", "저도",
    "박물관", "한독", "의약", "방문", "관람", "한독의약박물관",
}


def _simple_keyword_extract(text, n=5):
    """
    Gemini 호출 불가 시 Python으로 키워드 추출 (빈도 기반).
    한글 2글자 이상 단어에서 불용어를 제외하고 상위 n개 반환.
    """
    words = re.findall(r"[가-힣]{2,}", text)
    filtered = [w for w in words if w not in _STOPWORDS]
    if not filtered:
        return ["박물관", "관람", "후기", "전시", "방문"]
    counts = Counter(filtered)
    return [w for w, _ in counts.most_common(n)]


def check_forced_sentiment_direction(text, is_instagram=False):
    """
    텍스트에서 감성 방향만 빠르게 판단. (키워드/요약은 포함하지 않음)
    Returns: "긍정" | "부정" | None
    """
    if not text:
        return None

    if is_instagram:
        if any(tag in text for tag in INSTA_POSITIVE_HASHTAGS):
            return "긍정"

    if any(kw in text for kw in POSITIVE_KEYWORDS):
        return "긍정"

    if any(kw in text for kw in NEGATIVE_KEYWORDS):
        return "부정"

    return None


def _call_gemini_with_retry(client, prompt, max_retries=2):
    """
    Gemini API 호출.
    - 404(모델 없음): 다음 모델로 폴백
    - 429(할당량 초과): 10초 대기 후 1회만 재시도, 실패 시 RuntimeError 전파
    - 그 외 오류: 즉시 예외 전파
    """
    last_error = None
    for model_name in GEMINI_MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                return response
            except Exception as me:
                err_str = str(me).lower()
                last_error = me

                if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                    if attempt < max_retries - 1:
                        time.sleep(10)
                        continue
                    else:
                        raise RuntimeError(f"429_QUOTA: {me}") from me
                elif "404" in err_str or "not found" in err_str or "deprecated" in err_str or "invalid" in err_str:
                    break  # 다음 모델로
                else:
                    raise

    raise Exception(f"모든 Gemini 모델 시도 실패. 마지막 오류: {last_error}")


def _extract_via_gemini(text, api_key):
    """
    Gemini API로 키워드 5개 + 한줄 요약만 추출 (감성 판단 없음, 가벼운 프롬프트).
    Returns: "kw1, kw2, kw3, kw4, kw5 | 한줄요약" 형식 문자열 또는 None
    """
    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""아래 후기 본문에서 핵심 단어 5개와 한 줄 요약을 추출하세요.

반드시 아래 형식으로만 답하세요 (다른 설명 없이):
키워드1, 키워드2, 키워드3, 키워드4, 키워드5 | 한 줄 요약

규칙:
- 앞부분(|왼쪽): 후기 본문에 실제로 등장하는 핵심 단어 5개, 쉼표로 구분
- 뒷부분(|오른쪽): 방문자의 경험/감정을 중심으로 후기를 한 문장으로 요약
- '|' 구분자 반드시 포함

예시: 전시, 아이, 카페, 체험, 약학 | 아이와 함께 방문해 전시를 관람하고 카페에서 즐거운 시간을 보냈음

--- 후기 본문 ---
{text[:1500]}
"""
        response = _call_gemini_with_retry(client, prompt)
        result = response.text.strip()

        # 마크다운 볼드 제거
        result = re.sub(r"\*{1,2}", "", result).strip()

        # '|' 구분자가 있으면 유효한 응답
        if "|" in result:
            return result.split("\n")[0].strip()  # 첫 줄만
        return None
    except RuntimeError:
        return None  # 429 → 폴백으로 처리
    except Exception:
        return None


def analyze_sentiment_gemini(text, api_key, use_summary=True):
    """
    Gemini API로 감성분석 + 키워드 5개 + 한줄 요약 추출.
    Returns: (sentiment, "kw1, kw2, kw3, kw4, kw5 | 한줄요약")
    """
    if not text or not text.strip():
        return ("분석불가", "본문 내용 없음")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""아래는 수집된 게시물(블로그, 리뷰, SNS) 내용입니다.
이 후기가 '한독의약박물관(충북 음성 소재)' 또는 '한독의약박물관 서울관(강남구 청담동 소재)'과 관련된 내용인지 먼저 판단하세요.

만약 해당 박물관과 무관한 뉴스 기사, 보도자료, 혹은 다른 장소에 대한 글이라면 감성을 '부적합'으로 분류하세요.

박물관 관련 후기라면 '긍정', '중립', '부정' 중 하나로 분류하세요.
- 재미있다, 좋다, 만족, 추천, 유익, 즐겁다, 예쁘다 등 → 긍정
- 서비스 불만족, 시설 낙후, 볼거리 부족 등 → 부정
- 단순 정보 전달, 평이한 내용 → 중립

반드시 아래 형식만 사용해 답변하세요 (다른 설명 없이):
1. 관련성: 적합
2. 감성: 긍정
3. 내용 요약: 전시, 아이, 카페, 체험, 약학 | 아이와 함께 전시를 관람하고 카페에서 즐거운 시간을 보낸 긍정적인 후기

3번 규칙:
- 앞부분(|왼쪽): 본문에 실제로 나오는 핵심 단어 정확히 5개, 쉼표로 구분
- 뒷부분(|오른쪽): 방문자의 경험/감정 중심으로 한 문장 요약
- '|' 구분자 반드시 포함
"""
        if not use_summary:
            prompt = prompt.replace(
                "\n3. 내용 요약: 전시, 아이, 카페, 체험, 약학 | 아이와 함께 전시를 관람하고 카페에서 즐거운 시간을 보낸 긍정적인 후기",
                "\n3. 내용 요약: (생략)"
            )

        prompt += f"\n\n--- 게시물 본문 ---\n{text[:2000]}\n"

        response = _call_gemini_with_retry(client, prompt)
        res_text = response.text.strip()

        # 감성 파싱
        sentiment = "중립"
        relevance = "적합"

        rel_match = re.search(r"관련성[:\s]*(적합|부합|부적합|irrelevant|relevant)", res_text, re.I)
        if rel_match and ("부적합" in rel_match.group(1) or "irrelevant" in rel_match.group(1).lower()):
            relevance = "부적합"

        s_match = re.search(r"감성[:\s]*(긍정|부정|중립|부적합|Positive|Negative|Neutral|Irrelevant)", res_text, re.I)
        if s_match:
            raw = s_match.group(1).strip().lower()
            if "부적합" in raw or "irrelevant" in raw:    sentiment = "부적합"
            elif "긍정" in raw or "positive" in raw:      sentiment = "긍정"
            elif "부정" in raw or "negative" in raw:      sentiment = "부정"
            else:                                          sentiment = "중립"

        if relevance == "부적합":
            sentiment = "부적합"

        # 키워드+요약 파싱
        reason = ""
        r_patterns = [
            r"(?:\d+\.\s*)?내용\s*요약[:\s]+(.+?)(?=\n\d+\.|$)",
            r"(?:\d+\.\s*)?요약[:\s]+(.+?)(?=\n\d+\.|$)",
        ]
        for pat in r_patterns:
            m = re.search(pat, res_text, re.DOTALL | re.I)
            if m:
                candidate = m.group(1).strip()
                if candidate and "생략" not in candidate:
                    reason = candidate
                    break

        if not reason:
            # 폴백: 전체 응답에서 1번/2번 줄 제외 후 사용
            reason = re.sub(r"^\d+\.\s.*\n", "", res_text, flags=re.MULTILINE).strip()
            reason = re.sub(r"[*#]", "", reason).strip()

        reason = reason.replace("\n", " ").strip()
        reason = re.sub(r"\*{1,2}", "", reason).strip()
        if len(reason) > 300:
            reason = reason[:297] + "..."

        return (sentiment, reason)

    except RuntimeError as quota_err:
        # 429: 키워드+요약 폴백 처리
        return None, None  # 상위 함수에서 처리

    except Exception as e:
        return ("분석불가", f"Gemini 오류: {str(e)[:150]}")


def analyze_sentiment(text, api_key=None, mode="gemini", is_instagram=False, use_summary=True, rating=None):
    """
    감성 분석 메인 함수.
    - 감성 방향: 별점 > 강제 키워드 > Gemini 순으로 결정
    - 키워드+요약: 항상 Gemini에서 추출 (실패 시 Python 빈도 분석으로 폴백)
    """

    # 1. 감성 방향 결정
    if rating == "5" or rating == 5:
        forced_sentiment = "긍정"
    else:
        forced_sentiment = check_forced_sentiment_direction(text, is_instagram=is_instagram)

    # 2. Gemini 호출 (키워드+요약+감성 통합)
    effective_api_key = api_key or DEFAULT_API_KEY
    gemini_sentiment, reason = analyze_sentiment_gemini(text, effective_api_key, use_summary=use_summary)

    # 3. Gemini가 429로 실패한 경우 (None, None 반환)
    if gemini_sentiment is None:
        if use_summary:
            # Python 빈도 분석으로 키워드 추출
            kws = _simple_keyword_extract(text)
            kw_str = ", ".join(kws)
            # 요약: 본문 첫 문장 추출
            sentences = re.split(r"[.!?。\n]", text.strip())
            first_sent = next((s.strip() for s in sentences if len(s.strip()) > 10), "")
            summary = first_sent[:80] if first_sent else "Gemini 할당량 초과로 요약 불가"
            reason = f"{kw_str} | {summary}"
        else:
            reason = "Gemini 할당량 초과 (잠시 후 재시도 필요)"

        sentiment = forced_sentiment if forced_sentiment else "분석불가"
        return (sentiment, reason)

    # 4. 감성 최종 결정 (강제 키워드 > Gemini)
    if forced_sentiment:
        final_sentiment = forced_sentiment
    elif rating == "5" or rating == 5:
        final_sentiment = "긍정"
    else:
        final_sentiment = gemini_sentiment if gemini_sentiment else "중립"

    # 5. reason에 '|' 없으면 폴백 키워드 추가
    if use_summary and reason and "|" not in reason:
        kws = _simple_keyword_extract(text)
        reason = f"{', '.join(kws)} | {reason[:150]}"

    return (final_sentiment, reason)


# 하위 호환성 유지 (이전 코드가 check_forced_sentiment를 직접 import할 경우 대비)
def check_forced_sentiment(text, is_instagram=False):
    direction = check_forced_sentiment_direction(text, is_instagram)
    if direction is None:
        return None
    # 감성만 반환 (요약은 analyze_sentiment에서 Gemini로 처리)
    return (direction, f"{direction} 키워드 감지")
