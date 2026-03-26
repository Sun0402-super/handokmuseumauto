import os
import re
import io
import time
import json
import datetime

import streamlit as st
import pandas as pd

# ==============================
# 0) 기본 설정
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ⚠️ 결과 저장 폴더(기본값). 환경에 맞게 수정하거나, 사이드바에서 변경할 수 있습니다.
DEFAULT_RESULT_DIR = os.getenv(
    "RESULT_DIR",
    r"C:\Users\kr2200047\OneDrive - handokinc\J_ 한독의약박물관 - 문서\한독의약박물관 관람 후기",
)

# ⚠️ API Key는 코드에 하드코딩하지 않는 것을 권장합니다.
#    우선순위: Streamlit Secrets > 환경변수(GEMINI_API_KEY) > 빈 값
DEFAULT_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

# ==============================
# 1) 페이지 설정
# ==============================
st.set_page_config(
    page_title="한독의약박물관 후기 수집기",
    page_icon="💊",
    layout="wide",
)

# ==============================
# 2) 모듈 로드 (외부 크롤러)
# ==============================
modules_loaded = True
missing_modules_error = None

try:
    from naver_blog_crawling import crawl_naver_blog
    from daum_crawling import crawl_daum
    from kakao_map_crawling import crawl_kakao_map
    from google_map_crawling import run_google_maps_crawler
    from instagram_crawling import instagram_login, crawl_hashtag, crawl_location

    from driver_utils import setup_chrome_driver, clear_chrome_cache, kill_chrome_processes
    from sentiment_utils import analyze_sentiment
    from filter_utils import is_relevant_by_keywords

except ImportError as e:
    modules_loaded = False
    missing_modules_error = e

# ==============================
# 3) 커스텀 CSS
# ==============================
st.markdown(
    """
<style>
.log-container {
    font-family: monospace;
    background: #1e293b;
    color: #f1f5f9;
    padding: 10px;
    border-radius: 5px;
    height: 400px;
    overflow-y: auto;
}
.metric-container {
    display: flex;
    justify-content: space-between;
    gap: 15px;
    margin-bottom: 25px;
}
.metric-card {
    flex: 1;
    background: #262730;
    padding: 20px;
    border-radius: 12px;
    text-align: center;
    border: 1px solid #464855;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    transition: transform 0.2s;
}
.metric-card:hover {
    transform: translateY(-5px);
    border-color: #00ffcc;
}
.metric-label {
    font-size: 0.95rem;
    color: #a3a8b8;
    margin-bottom: 8px;
    font-weight: 500;
}
.metric-value {
    font-size: 2.2rem;
    font-weight: 800;
    color: #00ffcc;
    text-shadow: 0 0 10px rgba(0,255,204,0.3);
}
</style>
""",
    unsafe_allow_html=True,
)

# ==============================
# 4) 메인 UI
# ==============================
st.title("💊 한독의약박물관 후기 수집기")

if not modules_loaded:
    st.error(
        "필요한 크롤링 모듈을 로드하지 못했습니다.\n\n"
        f"- 에러: {missing_modules_error}\n\n"
        "같은 폴더(또는 PYTHONPATH)에 아래 모듈 파일들이 존재하는지 확인하세요:\n"
        "naver_blog_crawling.py, daum_crawling.py, kakao_map_crawling.py, google_map_crawling.py, "
        "instagram_crawling.py, driver_utils.py, sentiment_utils.py, filter_utils.py"
    )
    st.stop()

# ==============================
# 5) 세션 상태 초기화
# ==============================
def _init_state():
    if "results" not in st.session_state:
        st.session_state.results = []
    if "logs" not in st.session_state:
        st.session_state.logs = []
    if "excel_data" not in st.session_state:
        st.session_state.excel_data = None
    if "filename" not in st.session_state:
        st.session_state.filename = None
    if "is_finished" not in st.session_state:
        st.session_state.is_finished = False
    if "is_running" not in st.session_state:
        st.session_state.is_running = False


_init_state()

# ==============================
# 6) 데이터 가공 함수
# ==============================

def process_for_excel(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """플랫폼별 컬럼 구조 정의 및 가공 (연번 추가 + 분석이유 분리)"""

    def split_reason(row_dict):
        reason = row_dict.get("분석이유", "")
        kw, sm = "", ""
        if reason and "|" in reason:
            parts = reason.split("|", 1)
            kw = parts[0].strip()
            sm = parts[1].strip()
        return kw, sm

    new_rows = []
    for i, (_, row) in enumerate(df.iterrows(), 1):
        item = row.to_dict()
        kw, sm = split_reason(item)

        item["연번"] = i
        item["본문 키워드"] = kw
        item["한 줄 요약"] = sm

        # 인스타그램 해시태그 처리
        if source == "인스타그램":
            hashtags = ", ".join(re.findall(r"#(\w+)", item.get("본문내용", "")))
            item["해시태그(키워드)"] = hashtags if hashtags else kw

        new_rows.append(item)

    ndf = pd.DataFrame(new_rows)

    if source in ("네이버 블로그", "Daum 검색"):
        cols = [
            "연번",
            "출처",
            "작성일",
            "작성자",
            "제목",
            "본문내용",
            "URL",
            "본문 키워드",
            "분석이유",
            "한 줄 요약",
            "감성분석",
        ]

    elif source in ("구글 리뷰", "카카오맵 리뷰"):
        cols = [
            "연번",
            "출처",
            "작성자",
            "작성일",
            "별점",
            "본문내용",
            "URL",
            "본문 키워드",
            "한 줄 요약",
            "감성분석",
        ]

    elif source == "인스타그램":
        cols = [
            "연번",
            "출처",
            "작성일",
            "작성자",
            "본문내용",
            "해시태그(키워드)",
            "URL",
            "분석이유",
            "한 줄 요약",
            "감성분석",
        ]

    else:
        cols = ndf.columns.tolist()

    existing_cols = [c for c in cols if c in ndf.columns]
    return ndf[existing_cols]


def process_for_unified_excel(df: pd.DataFrame) -> pd.DataFrame:
    """통합 보고서용 컬럼 가공 (A열: 연번, B~H열 구성)"""
    unified_data = []

    for i, (_, item) in enumerate(df.iterrows(), 1):
        src = item.get("출처", "")
        reason = item.get("분석이유", "")

        kw, sm = "", ""
        if reason and "|" in reason:
            parts = reason.split("|", 1)
            kw = parts[0].strip()
            sm = parts[1].strip()

        # 날짜 포맷팅 (yyyy-mm-dd)
        raw_date = item.get("작성일", "-")
        formatted_date = str(raw_date)
        if raw_date and len(str(raw_date)) >= 8:
            d_match = re.search(r"(\d{4})[.\-/ ](\d{1,2})[.\-/ ](\d{1,2})", str(raw_date))
            if d_match:
                yyyy, mm, dd = d_match.group(1), int(d_match.group(2)), int(d_match.group(3))
                formatted_date = f"{yyyy}-{mm:02d}-{dd:02d}"

        if src == "인스타그램":
            hashtags = ", ".join(re.findall(r"#(\w+)", item.get("본문내용", "")))
            kw_val = hashtags if hashtags else kw
        else:
            kw_val = kw

        unified_row = {
            "연번": i,
            "플랫폼": src,
            "작성일": formatted_date,
            "긍정/부정(감성분석)": item.get("감성분석", ""),
            "분석 이유": reason,
            "본문 키워드": kw_val,
            "한줄 요약": sm,
            "URL": item.get("URL", "-"),
        }
        unified_data.append(unified_row)

    res_df = pd.DataFrame(unified_data)
    target_cols = [
        "연번",
        "플랫폼",
        "작성일",
        "긍정/부정(감성분석)",
        "분석 이유",
        "본문 키워드",
        "한줄 요약",
        "URL",
    ]
    return res_df[target_cols]


def save_with_autofit(df: pd.DataFrame, filepath, sheet_name: str = "Sheet1"):
    """엑셀 저장 시 셀 너비를 내용에 맞춰 자동 조절"""
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                val = "" if cell.value is None else str(cell.value)
                length = sum(2 if ord(c) > 128 else 1 for c in val)
                max_length = max(max_length, length)

            adjusted_width = max_length + 2
            ws.column_dimensions[column].width = min(max(adjusted_width, 10), 80)


def save_multi_sheets(file_dest, df_list, sheet_names):
    """여러 시트로 저장 + 컬럼 너비 자동 조절 (file_dest: 경로(str) 또는 BytesIO)"""
    with pd.ExcelWriter(file_dest, engine="openpyxl") as writer:
        for d, s in zip(df_list, sheet_names):
            d.to_excel(writer, index=False, sheet_name=s)
            ws = writer.sheets[s]

            for col in ws.columns:
                max_len = 0
                column = col[0].column_letter
                for cell in col:
                    val = "" if cell.value is None else str(cell.value)
                    length = sum(2 if ord(c) > 128 else 1 for c in val)
                    max_len = max(max_len, length)
                ws.column_dimensions[column].width = min(max(max_len + 2, 10), 80)


# ==============================
# 7) 로그/화면 업데이트 함수
# ==============================

def update_logs(msg: str, log_placeholder=None):
    st.session_state.logs.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    if log_placeholder is not None:
        log_html = (
            "<div class='log-container'>" + "<br>".join(reversed(st.session_state.logs)) + "</div>"
        )
        log_placeholder.markdown(log_html, unsafe_allow_html=True)


def compute_metrics():
    total = len(st.session_state.results)
    naver = len([r for r in st.session_state.results if r.get("출처") == "네이버 블로그"])
    daum = len([r for r in st.session_state.results if r.get("출처") == "Daum 검색"])
    kakao = len([r for r in st.session_state.results if r.get("출처") == "카카오맵 리뷰"])
    google = len([r for r in st.session_state.results if r.get("출처") == "구글 리뷰"])
    insta = len([r for r in st.session_state.results if r.get("출처") == "인스타그램"])
    pos = len([r for r in st.session_state.results if r.get("감성분석") == "긍정"])
    return total, naver, daum, kakao, google, insta, pos


def render_metrics(stats_placeholder):
    total, naver, daum, kakao, google, insta, pos = compute_metrics()
    metrics_html = f"""
    <div class='metric-container'>
        <div class='metric-card'>
            <div class='metric-label'>네이버 블로그</div>
            <div class='metric-value'>{naver}건</div>
        </div>
        <div class='metric-card'>
            <div class='metric-label'>다음/카카오맵</div>
            <div class='metric-value'>{daum + kakao}건</div>
        </div>
        <div class='metric-card'>
            <div class='metric-label'>구글 지도 리뷰</div>
            <div class='metric-value'>{google}건</div>
        </div>
        <div class='metric-card'>
            <div class='metric-label'>인스타그램</div>
            <div class='metric-value'>{insta}건</div>
        </div>
    </div>
    <div style='text-align: center; color: #a3a8b8; font-size: 0.9rem; margin-top: -10px; margin-bottom: 20px;'>
        총 {total}건 수집 중 (심층 분석 완료: {pos}건)
    </div>
    """
    stats_placeholder.markdown(metrics_html, unsafe_allow_html=True)


# ==============================
# 8) 사이드바 UI
# ==============================

with st.sidebar:
    st.header("⚙️ 설정")

    # 결과 저장 폴더
    result_dir = st.text_input("결과 저장 폴더(로컬 경로)", value=DEFAULT_RESULT_DIR)
    os.makedirs(result_dir, exist_ok=True)

    # API KEY
    api_key = st.text_input(
        "GEMINI_API_KEY (Secrets/환경변수 사용 권장)",
        value=DEFAULT_API_KEY,
        type="password",
        help="Streamlit Cloud/서버에서는 secrets.toml 또는 환경변수로 관리하세요.",
    )

    st.subheader("옵션")
    use_summary = st.checkbox("요약 사용", value=True)
    use_sentiment = st.checkbox("감성 분석 사용", value=True)

    st.subheader("대상")
    do_naver = st.checkbox("네이버 블로그", value=True)
    do_daum = st.checkbox("다음 검색", value=True)
    do_kakao = st.checkbox("카카오맵 리뷰", value=True)
    do_google = st.checkbox("구글 지도 리뷰", value=True)
    do_insta = st.checkbox("인스타그램", value=True)

    st.divider()

    show_live_view = st.checkbox(
        "📺 실시간 화면 보기",
        value=True,
        help="크롤링 중인 브라우저 화면을 하단에 작게 보여줍니다.",
    )

    st.subheader("인스타그램(선택)")
    insta_max_posts = st.number_input("최대 수집 게시물 수", min_value=1, max_value=500, value=100, step=10)

    # ⚠️ 보안: 아이디/비번 하드코딩 금지. 입력받되 password 형태로.
    insta_id = st.text_input(
        "Instagram ID",
        value=st.secrets.get("INSTA_ID", os.getenv("INSTA_ID", "")),
        help="서버에 올릴 경우 secrets/환경변수로 관리하세요.",
    )
    insta_pw = st.text_input(
        "Instagram Password",
        value=st.secrets.get("INSTA_PW", os.getenv("INSTA_PW", "")),
        type="password",
    )

    start_clicked = st.button("🚀 크롤링 시작", use_container_width=True)

    if st.session_state.is_finished:
        st.write("---")
        if st.session_state.results:
            st.success("✅ 수집 및 분석 완료!")
            if st.session_state.excel_data:
                st.download_button(
                    label="📥 결과 다운로드 (Excel)",
                    data=st.session_state.excel_data,
                    file_name=st.session_state.filename,
                    key="download_btn_sidebar",
                    use_container_width=True,
                )
            else:
                st.info("ℹ️ 결과가 [후기] 폴더에 저장되었습니다.")
        else:
            st.warning("⚠️ 수집된 결과가 없습니다.")


# ==============================
# 9) 본문 레이아웃
# ==============================

col_log, col_res = st.columns([1, 2])

with col_log:
    st.subheader("📡 로그")
    log_placeholder = st.empty()

with col_res:
    st.subheader("📊 결과 요약")
    stats_placeholder = st.empty()
    res_list_placeholder = st.empty()

    if st.session_state.is_finished:
        if st.session_state.results:
            st.success(f"✅ 총 {len(st.session_state.results)}건의 후기 수집이 완료되었습니다!")
            if st.session_state.excel_data:
                st.download_button(
                    label="📥 수집된 결과 엑셀 다운로드 (통합 보고서)",
                    data=st.session_state.excel_data,
                    file_name=st.session_state.filename,
                    key="download_btn_main",
                    use_container_width=True,
                )
            else:
                st.info("ℹ️ 플랫폼별 개별 엑셀 파일은 저장 폴더에 저장되었습니다.")
        else:
            st.warning("⚠️ 수집된 결과가 없습니다. 옵션을 확인해 주세요.")

    live_view_placeholder = st.empty()
    if st.session_state.is_running:
        st.markdown("---")
        st.caption("📺 실시간 크롤링 화면 (Live View)")


# 최초 렌더
render_metrics(stats_placeholder)


# ==============================
# 10) 크롤링 실행
# ==============================

if start_clicked:
    # 실행 전 초기화
    st.session_state.results = []
    st.session_state.logs = []
    st.session_state.excel_data = None
    st.session_state.filename = None
    st.session_state.is_finished = False
    st.session_state.is_running = True

    render_metrics(stats_placeholder)
    update_logs("🚀 크롤링을 시작합니다.", log_placeholder)

    try:
        update_logs("기존 브라우저 프로세스 정리 중...", log_placeholder)
        try:
            kill_chrome_processes()
            time.sleep(1)
        except Exception:
            pass

        # 1) 네이버 블로그
        if do_naver:
            update_logs("네이버 블로그 수집 중...", log_placeholder)
            try:
                naver_count = 0
                for item in crawl_naver_blog("한독의약박물관", 1, api_key, use_sentiment, use_summary):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(
                                    item["data"], caption="현재 수집 중인 화면", use_container_width=True
                                )
                            continue

                        is_rel, reason = is_relevant_by_keywords(item.get("본문내용", ""), item.get("제목", ""))
                        if not is_rel:
                            update_logs(
                                f"⏩ [제외] {item.get('제목', '제목없음')[:15]}... ({reason})",
                                log_placeholder,
                            )
                            continue
                        if item.get("감성분석") == "부적합":
                            update_logs(
                                f"⏩ [제외] {item.get('제목', '제목없음')[:15]}... (AI 판단: 관련 없음)",
                                log_placeholder,
                            )
                            continue

                        st.session_state.results.append(item)
                        naver_count += 1
                        render_metrics(stats_placeholder)
                    else:
                        update_logs(str(item), log_placeholder)

                if naver_count == 0:
                    update_logs(
                        "⚠ 네이버 블로그에서 최근 1주일간 검색된 결과가 없습니다. (필터링 기준을 확인하세요)",
                        log_placeholder,
                    )
                else:
                    update_logs(f"✅ 네이버 블로그 {naver_count}건 수집 완료!", log_placeholder)

            except Exception as e:
                import traceback

                update_logs(f"네이버 오류: {e}", log_placeholder)
                update_logs(traceback.format_exc(), log_placeholder)

        # 2) 다음 검색
        if do_daum:
            update_logs("다음 검색 수집 중...", log_placeholder)
            try:
                daum_count = 0
                for item in crawl_daum("한독의약박물관", 1, api_key, use_sentiment, use_summary):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(
                                    item["data"], caption="현재 수집 중인 화면", use_container_width=True
                                )
                            continue

                        is_rel, reason = is_relevant_by_keywords(item.get("본문내용", ""), item.get("제목", ""))
                        if not is_rel:
                            update_logs(
                                f"⏩ [제외] {item.get('제목', '제목없음')[:15]}... ({reason})",
                                log_placeholder,
                            )
                            continue

                        st.session_state.results.append(item)
                        daum_count += 1
                        render_metrics(stats_placeholder)
                    else:
                        update_logs(str(item), log_placeholder)

                update_logs(f"✅ 다음 검색 {daum_count}건 수집 완료!", log_placeholder)

            except Exception as e:
                update_logs(f"다음 오류: {e}", log_placeholder)

        # 3) 카카오맵 리뷰
        if do_kakao:
            update_logs("카카오맵 리뷰 수집 중...", log_placeholder)
            try:
                kakao_count = 0
                for item in crawl_kakao_map(api_key, use_sentiment, use_summary):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(
                                    item["data"], caption="현재 수집 중인 화면", use_container_width=True
                                )
                            continue

                        st.session_state.results.append(item)
                        kakao_count += 1
                        render_metrics(stats_placeholder)
                    else:
                        update_logs(str(item), log_placeholder)

                update_logs(f"✅ 카카오맵 리뷰 {kakao_count}건 수집 완료!", log_placeholder)

            except Exception as e:
                update_logs(f"카카오맵 오류: {e}", log_placeholder)

        # 4) 구글 지도 리뷰
        if do_google:
            update_logs("구글 지도 리뷰 수집 중...", log_placeholder)
            try:
                google_count = 0
                for item in run_google_maps_crawler(api_key, use_sentiment, use_summary):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(
                                    item["data"], caption="현재 수집 중인 화면", use_container_width=True
                                )
                            continue

                        st.session_state.results.append(item)
                        google_count += 1
                        render_metrics(stats_placeholder)
                    else:
                        update_logs(str(item), log_placeholder)

                update_logs(f"✅ 구글 지도 리뷰 {google_count}건 수집 완료!", log_placeholder)

            except Exception as e:
                update_logs(f"구글 오류: {e}", log_placeholder)

        # 5) 인스타그램
        if do_insta:
            update_logs("인스타그램 수집 시작...", log_placeholder)
            if not insta_id or not insta_pw:
                update_logs("⚠️ 인스타그램 ID/PW가 비어 있어 인스타그램 수집을 건너뜁니다.", log_placeholder)
            else:
                try:
                    driver, status = setup_chrome_driver(headless=True, use_profile=True)
                    if not driver:
                        update_logs("❌ 브라우저를 시작할 수 없습니다.", log_placeholder)
                    else:
                        driver.minimize_window()
                        if instagram_login(driver, insta_id, insta_pw):
                            insta_count = 0

                            # 5-1) 해시태그
                            update_logs("📸 해시태그(#한독의약박물관) 수집 중...", log_placeholder)
                            for item in crawl_hashtag(
                                driver,
                                "한독의약박물관",
                                int(insta_max_posts),
                                api_key,
                                use_sentiment,
                                use_summary,
                            ):
                                if isinstance(item, dict):
                                    if item.get("type") == "screenshot":
                                        if show_live_view:
                                            live_view_placeholder.image(
                                                item["data"],
                                                caption="현재 수집 중인 화면",
                                                use_container_width=True,
                                            )
                                        continue

                                    if not any(r.get("URL") == item.get("URL") for r in st.session_state.results):
                                        st.session_state.results.append(item)
                                        insta_count += 1
                                        render_metrics(stats_placeholder)
                                else:
                                    update_logs(str(item), log_placeholder)

                            # 5-2) 장소(Location) 기반
                            update_logs("📍 장소(Location) 기반 수집 중...", log_placeholder)
                            # 109120676658159: 한독의약박물관 공식 장소 ID
                            for item in crawl_location(
                                driver,
                                "109120676658159",
                                int(insta_max_posts),
                                api_key,
                                use_sentiment,
                                use_summary,
                            ):
                                if isinstance(item, dict):
                                    if item.get("type") == "screenshot":
                                        if show_live_view:
                                            live_view_placeholder.image(
                                                item["data"],
                                                caption="현재 수집 중인 화면",
                                                use_container_width=True,
                                            )
                                        continue

                                    if not any(r.get("URL") == item.get("URL") for r in st.session_state.results):
                                        st.session_state.results.append(item)
                                        insta_count += 1
                                        render_metrics(stats_placeholder)
                                else:
                                    update_logs(str(item), log_placeholder)

                            update_logs(f"✅ 인스타그램 {insta_count}건 수집 완료!", log_placeholder)

                        driver.quit()

                except Exception as e:
                    update_logs(f"인스타그램 오류: {e}", log_placeholder)

        # 6) 결과 저장
        if st.session_state.results:
            update_logs("💾 결과 파일 저장 중...", log_placeholder)
            try:
                df = pd.DataFrame(st.session_state.results)
                today = datetime.datetime.now().strftime("%Y%m%d")

                target_dir = os.path.join(result_dir, f"[Data_{today}]")
                os.makedirs(target_dir, exist_ok=True)

                # 플랫폼별 저장
                platforms = sorted(set([r.get("출처", "") for r in st.session_state.results if r.get("출처")]))
                for src in platforms:
                    sdf = df[df["출처"] == src]
                    if not sdf.empty:
                        pdf = process_for_excel(sdf, src)
                        fname = f"{src}_{today}.xlsx"
                        save_with_autofit(pdf, os.path.join(target_dir, fname), sheet_name=src[:31])  # sheet name limit

                # 통합 보고서 저장
                unified_df = process_for_unified_excel(df)
                positive_df = unified_df[unified_df["긍정/부정(감성분석)"] == "긍정"].copy()
                positive_df["연번"] = range(1, len(positive_df) + 1)

                unified_fname = f"{today}_한독의약박물관 관람 후기.xlsx"
                unified_filepath = os.path.join(target_dir, unified_fname)

                save_multi_sheets(unified_filepath, [unified_df, positive_df], ["전체 후기", "긍정 후기"])

                # 다운로드 버튼용 Bytes
                output = io.BytesIO()
                save_multi_sheets(output, [unified_df, positive_df], ["전체 후기", "긍정 후기"])

                st.session_state.excel_data = output.getvalue()
                st.session_state.filename = unified_fname

                update_logs(f"✅ 저장 완료: {target_dir}", log_placeholder)

            except Exception as e:
                update_logs(f"⚠️ 파일 저장 오류: {e}", log_placeholder)

        else:
            update_logs("⚠️ 수집된 결과가 없습니다. (필터/옵션을 확인하세요)", log_placeholder)

    finally:
        st.session_state.is_finished = True
        st.session_state.is_running = False
        update_logs("🏁 모든 작업 완료!", log_placeholder)
        st.rerun()
