import os
import re
import time

# Gemini API 관련
DEFAULT_API_KEY = "AIzaSyDLD7stdtusDTxCYrqonQiL4S5m050X98s"

# 사용 가능한 Gemini 모델 (우선순위 순)
GEMINI_MODELS = [
    "gemini-2.0-flash-lite",      # 기본 (저렴/빠름)
    "gemini-2.0-flash",           # 폴백 1
    "gemini-1.5-flash",           # 폴백 2
    "gemini-1.5-flash-latest",    # 폴백 3
]

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
    "불친절", "실망", "별로", "좁다", "아쉽다", "주차 불편", "전시 빈약",
    "설명 부족", "볼게 없음", "노잼", "비추", "다시는 안 가", "다신 안 가",
    "불편", "재미없다", "재미 없다", "재방문 의사 없음", "재방문 의사가 없", "다시 안 올", "또 오고 싶지 않"
]


def check_forced_sentiment(text, is_instagram=False):
    """
    텍스트 내에 특정 긍정/부정 키워드가 포함되어 있는지 확인합니다.
    매칭된 키워드를 최대 5개 모아 'kw1, kw2 | 요약' 형식으로 반환합니다.
    """
    if not text:
        return None

    # 1. 인스타그램 전용 긍정 해시태그 체크 (모두 수집)
    if is_instagram:
        matched_tags = [tag for tag in INSTA_POSITIVE_HASHTAGS if tag in text]
        if matched_tags:
            kw_str = ", ".join(t.lstrip("#") for t in matched_tags[:5])
            summary = f"인스타그램 긍정 해시태그 {len(matched_tags)}개 감지"
            return ("긍정", f"{kw_str} | {summary}")

    # 2. 일반 긍정 키워드 체크 (모두 수집, 최대 5개)
    matched_pos = [kw for kw in POSITIVE_KEYWORDS if kw in text]
    if matched_pos:
        kw_str = ", ".join(matched_pos[:5])
        # 한 줄 요약: 첫 매칭 키워드 기반으로 문장 생성
        summary = f"긍정 표현({matched_pos[0]} 등) 포함된 후기"
        return ("긍정", f"{kw_str} | {summary}")

    # 3. 일반 부정 키워드 체크 (모두 수집, 최대 5개)
    matched_neg = [kw for kw in NEGATIVE_KEYWORDS if kw in text]
    if matched_neg:
        kw_str = ", ".join(matched_neg[:5])
        summary = f"부정 표현({matched_neg[0]} 등) 포함된 후기"
        return ("부정", f"{kw_str} | {summary}")

    return None


def _call_gemini_with_retry(client, prompt, max_retries=2):
    """
    Gemini API 호출.
    - 404(모델 없음): 다음 모델로 폴백
    - 429(할당량 초과): 10초 대기 후 1회만 재시도, 실패 시 예외 전파
    - 그 외 오류: 즉시 예외 전파
    """
    last_error = None

    for model_name in GEMINI_MODELS:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                return response  # 성공
            except Exception as me:
                err_str = str(me).lower()
                last_error = me

                if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                    if attempt < max_retries - 1:
                        # 첫 번째 시도: 10초 대기 후 재시도
                        time.sleep(10)
                        continue
                    else:
                        # 재시도 실패 → 429 예외 즉시 전파 (\ub2e4른 모델로 넘겨도 당관 할당량이 대부분 저하되어 있음)
                        raise RuntimeError(f"429_QUOTA: {me}") from me
                elif "404" in err_str or "not found" in err_str or "deprecated" in err_str or "invalid" in err_str:
                    break  # 모델 없음: 다음 모델로
                else:
                    raise  # 그 외 오류

    raise Exception(f"모든 Gemini 모델 시도 실패. 마지막 오류: {last_error}")


def analyze_sentiment_gemini(text, api_key, use_summary=True):
    if not text or not text.strip():
        return ("분석불가", "본문 내용 없음")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""아래는 수집된 게시물(블로그, 리뷰, SNS) 내용입니다.
이 후기가 '한독의약박물관(충북 음성 소재)' 또는 '한독의약박물관 서울관(강남구 청담동 소재)'과 관련된 내용인지 먼저 판단하세요.

만약 해당 박물관과 무관한 뉴스 기사, 보도자료, 혹은 다른 장소(예: 떡박물관 등)에 대한 글이라면 감성을 '부적합'으로 분류하세요.

박물관과 관련된 후기라면, 아래 기준에 따라 '긍정', '중립', '부정' 중 하나로 분류하세요.
- 재미있다, 좋다, 만족, 추천, 유익, 즐겁다, 감사하다, 예쁘다, 가볼만하다 등의 표현이 있거나,
- 직원이 친절함, 시설이 깨끗함/쾌적함, 주차가 편리함, 전시가 체계적임 등의 긍정적 측면이 서술되었다면 적극적으로 '긍정'으로 분류하세요.
- 특히 박물관 내 카페나 공원(산책로) 시설이 좋았다는 언급, 혹은 박물관과 관련된 체험 프로그램(예: 토크콘서트 등)이 즐거웠다는 내용은 매우 긍정적인 후기입니다.
- 과거의 편견(지루할 줄 알았는데 아니었다 등)을 언급하며 반전된 긍정적 감정을 표현한 경우에도 '긍정'으로 분류해야 합니다.
- 반대로 서비스 불만족, 시설 낙후, 볼거리 부족 등의 내용이 있다면 '부정'으로 분류하세요.
- 단순 정보 전달이거나 긍정도 부정도 아닌 평이한 내용은 '중립'으로 분류하세요.

반드시 아래 형식만 사용해 답변하세요 (다른 설명 없이):
1. 관련성: 적합
2. 감성: 긍정
3. 내용 요약: 전시, 아이, 카페, 체험, 박물관 | 아이와 함께 전시를 관람하고 카페에서 즐거운 시간을 보낸 긍정적인 후기

위 예시처럼 3번 항목은 반드시 '키워드1, 키워드2, 키워드3, 키워드4, 키워드5 | 한 줄 요약' 형식이어야 합니다.
- 앞부분(|왼쪽): 본문에 실제로 나오는 핵심 단어 5개를 쉼표로 구분
- 뒷부분(|오른쪽): 후기 내용을 한 문장으로 요약 (방문자의 경험/감정 중심)
- '|' 구분자는 반드시 포함해야 합니다
"""
        if not use_summary:
            # 요약 불필요 시 3번 항목 지시 제거
            prompt = prompt.replace(
                "\n3. 내용 요약: 전시, 아이, 카페, 체험, 박물관 | 아이와 함께 전시를 관람하고 카페에서 즐거운 시간을 보낸 긍정적인 후기",
                "\n3. 내용 요약: (생략)"
            )

        prompt += f"\n\n--- 게시물 본문 ---\n{text[:2000]}\n"

        response = _call_gemini_with_retry(client, prompt)
        res_text = response.text.strip()

        sentiment = "중립"
        reason = ""

        # 1. 관련성 추출
        relevance = "적합"
        rel_match = re.search(r"관련성[:\s]*(적합|부합|부적합|irrelevant|relevant)", res_text, re.I)
        if rel_match:
            if "부적합" in rel_match.group(1) or "irrelevant" in rel_match.group(1).lower():
                relevance = "부적합"

        # 2. 감성 추출
        s_match = re.search(r"감성[:\s]*(긍정|부정|중립|부적합|Positive|Negative|Neutral|Irrelevant)", res_text, re.I)
        if s_match:
            raw = s_match.group(1).strip().lower()
            if "부적합" in raw or "irrelevant" in raw:
                sentiment = "부적합"
            elif "긍정" in raw or "positive" in raw:
                sentiment = "긍정"
            elif "부정" in raw or "negative" in raw:
                sentiment = "부정"
            else:
                sentiment = "중립"

        if relevance == "부적합":
            sentiment = "부적합"

        # 3. 내용 요약 추출 ('3. 내용 요약:' 형식 우선)
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

        # 폴백: 요약 못 찾은 경우
        if not reason:
            reason = re.sub(r"^\d+\.\s.*?\n", "", res_text, flags=re.MULTILINE).strip()
            reason = re.sub(r"[*#]", "", reason).strip()

        # 정리
        reason = reason.replace("\n", " ").strip()
        reason = re.sub(r"\*{1,2}", "", reason).strip()
        if len(reason) > 300:
            reason = reason[:297] + "..."

        return (sentiment, reason)

    except RuntimeError as quota_err:
        # 429 통신 처리: Gemini 호출 불가 시 텍스트 키워드 기반 입력 결과로 대체
        forced = check_forced_sentiment(text)
        if forced:
            return forced
        return ("분석불가", f"Gemini 할당량 초과 (잠시 후 재시도 필요) - 키워드 분석으로 대체")
    except Exception as e:
        return ("분석불가", f"Gemini 오류: {str(e)[:150]}")


def analyze_sentiment(text, api_key=None, mode="gemini", is_instagram=False, use_summary=True, rating=None):
    """모드에 따라 감성 분석 수행 (기본은 gemini)"""

    # -1. 별점 체크 (별점 5점이면 무조건 긍정 - 사용자 요청)
    if rating == "5" or rating == 5:
        return ("긍정", "별점 5점 | 별점 5점 만점으로 자동 긍정 분류")

    # 0. 우선 순위 키워드 체크
    forced_res = check_forced_sentiment(text, is_instagram=is_instagram)
    if forced_res:
        return forced_res

    # Gemini API 기반 감성 분석
    return analyze_sentiment_gemini(text, api_key or DEFAULT_API_KEY, use_summary=use_summary)
