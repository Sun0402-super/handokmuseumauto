import streamlit as st
import pandas as pd
import datetime
import os
import time
import json
import io
import sys

# [수정] 배포 환경(Streamlit Cloud 등)에서의 로컬 모듈 인식 문제 해결을 위해 현재 경로를 최우선 순위로 추가
import os
import sys

# 현재 파일의 절대 경로 기준 디렉토리를 찾습니다.
current_dir = os.path.dirname(os.path.abspath(__file__))

# sys.path의 가장 처음에 현재 디렉토리를 추가하여 로컬 모듈이 최우선으로 검색되게 합니다.
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# BASE_DIR 명시
BASE_DIR = current_dir

# ⚠️ 결과 저장 폴더(기본값). 환경에 맞게 수정하거나, 사이드바에서 변경할 수 있습니다.
if sys.platform == 'win32':
    DEFAULT_RESULT_DIR = r"C:\Users\kr2200047\OneDrive - handokinc\J_ 한독의약박물관 - 문서\한독의약박물관 관람 후기"
else:
    DEFAULT_RESULT_DIR = os.path.join(BASE_DIR, "reviews")

os.makedirs(DEFAULT_RESULT_DIR, exist_ok=True)
RESULT_DIR = DEFAULT_RESULT_DIR # 전역 변수 유지

# ⚠️ API Key는 코드에 하드코딩하지 않는 것을 권장합니다.
DEFAULT_API_KEY = "AIzaSyDLD7stdtusDTxCYrqonQiL4S5m050X98s"

# 페이지 설정
st.set_page_config(
    page_title="한독의약박물관 후기 수집기",
    page_icon="💊",
    layout="wide"
)

# 모듈 로드 시도
try:
    from naver_blog_crawling import crawl_naver_blog
    from daum_crawling import crawl_daum
    from kakao_map_crawling import crawl_kakao_map
    from google_map_crawling import run_google_maps_crawler
    from instagram_crawling import instagram_login, crawl_hashtag, crawl_location, crawl_tagged_posts
    from driver_utils import setup_chrome_driver, clear_chrome_cache, kill_chrome_processes
    from sentiment_utils import analyze_sentiment
    from filter_utils import is_relevant_by_keywords
    modules_loaded = True
except ImportError as e:
    st.error(f"❌ 필요한 크롤링 모듈을 로드하지 못했습니다: {e}")
    
    # 상세 진단 정보 출력 (배포 환경 디버깅용)
    with st.expander("🔍 상세 진단 정보 (Streamlit Cloud 환경 확인)"):
        st.write(f"**현재 작업 경로 (CWD):** `{os.getcwd()}`")
        st.write(f"**현재 파일 경로 (__file__):** `{__file__}`")
        st.write(f"**시스템 경로 (sys.path):**")
        st.write(sys.path)
        
        st.write("**현재 디렉토리 파일 목록:**")
        try:
            files = os.listdir(os.getcwd())
            st.write(files)
        except Exception as err:
            st.write(f"파일 목록을 읽을 수 없습니다: {err}")
            
    st.info("💡 **해결 방법:** GitHub에 모든 `.py` 파일(특히 `naver_blog_crawling.py` 등)이 업로드되었는지 확인해 주세요. 또한 `requirements.txt`에 필요한 패키지가 모두 포함되어 있는지 확인이 필요합니다.")
    modules_loaded = False

# 커스텀 CSS
st.markdown("""
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
    """, unsafe_allow_html=True)

# 메인 UI
st.title("💊 한독의약박물관 후기 수집기")

if not modules_loaded:
    st.stop()

# 세션 상태 초기화
if 'results' not in st.session_state: st.session_state.results = []
if 'logs' not in st.session_state: st.session_state.logs = []
if 'excel_data' not in st.session_state: st.session_state.excel_data = None
if 'filename' not in st.session_state: st.session_state.filename = None
if 'is_finished' not in st.session_state: st.session_state.is_finished = False
if 'is_running' not in st.session_state: st.session_state.is_running = False

# 데이터 가공용 함수 정의
def process_for_excel(df, source):
    """플랫폼별 컬럼 구조 정의 및 가공 (사용자 최신 요청 반영: 연번 추가)"""
    import re
    
    # 분석이유(키워드 | 요약) 분리 헬퍼
    def split_reason(row):
        import re
        reason = row.get('분석이유', '')
        kw, sm = "", ""
        if not reason:
            return kw, sm
        if "|" in reason:
            # Gemini가 "키워드1, 키워드2 | 한줄요약" 형식으로 응답한 경우
            parts = reason.split("|", 1)
            kw = parts[0].strip()
            sm = parts[1].strip()
        else:
            # 강제 키워드 감지 결과 (예: "긍정 키워드('좋다') 포함") 처리
            # 작은따옴표 안의 단어를 키워드로 추출
            quoted = re.findall(r"'([^']+)'", reason)
            kw = ", ".join(quoted) if quoted else ""
            sm = reason  # 이유 전체를 한줄요약으로 사용
        return kw, sm

    new_rows = []
    for i, (_, row) in enumerate(df.iterrows(), 1):
        kw, sm = split_reason(row)
        item = row.to_dict()
        item['연번'] = i
        item['본문 키워드'] = kw
        item['한 줄 요약'] = sm
        
        # 인스타그램 해시태그 처리
        if source == '인스타그램':
            hashtags = ", ".join(re.findall(r'#(\w+)', item.get('본문내용', '')))
            item['해시태그(키워드)'] = hashtags if hashtags else kw
            
        new_rows.append(item)
    
    ndf = pd.DataFrame(new_rows)
    
    if source == '네이버 블로그' or source == 'Daum 검색':
        # A:연번, B:출처, C:작성일, D:작성자, E:제목, F:본문내용, G:URL, H:본문 키워드, I:분석이유, J:한 줄 요약, K:감성분석
        # (사용자 요청에 맞추기 위해 작성일/작성자 순서 조정: C열에 작성일이 와야 통합보고서 매핑이 용이)
        cols = ['연번', '출처', '작성일', '작성자', '제목', '본문내용', 'URL', '본문 키워드', '분석이유', '한 줄 요약', '감성분석']
    elif source == '구글 리뷰' or source == '카카오맵 리뷰':
        # A:연번, B:출처, C:작성자, D:작성일, E:별점, F:본문내용, G:URL, H:본문 키워드, I:한 줄 요약, J:감성분석
        cols = ['연번', '출처', '작성자', '작성일', '별점', '본문내용', 'URL', '본문 키워드', '한 줄 요약', '감성분석']
    elif source == '인스타그램':
        # A:연번, B:출처, C:작성일, D:작성자, E:본문내용, F:해시태그(키워드), G:URL, H:분석 이유, I:한 줄 요약, J:감성분석
        cols = ['연번', '출처', '작성일', '작성자', '본문내용', '해시태그(키워드)', 'URL', '분석이유', '한 줄 요약', '감성분석']
    else:
        cols = ndf.columns.tolist()
    
    existing_cols = [c for c in cols if c in ndf.columns]
    return ndf[existing_cols]

def process_for_unified_excel(df):
    """통합 보고서용 컬럼 가공 (A열: 연번 도입, B~H열 구성)"""
    import re
    unified_data = []
    for i, (_, item) in enumerate(df.iterrows(), 1):
        src = item.get('출처', '')
        reason = item.get('분석이유', '')
        kw, sm = "", ""
        if reason and "|" in reason:
            parts = reason.split("|", 1)
            kw = parts[0].strip()
            sm = parts[1].strip()
        elif reason:
            # 강제 키워드 감지 결과 처리 (따옴표 안 단어 → 키워드)
            quoted = re.findall(r"'([^']+)'", reason)
            kw = ", ".join(quoted) if quoted else ""
            sm = reason
        
        # 날짜 포맷팅 (yyyy-mm-dd)
        raw_date = item.get('작성일', '-')
        formatted_date = raw_date
        if raw_date and len(str(raw_date)) >= 8:
            try:
                # 다양한 날짜 형식 대응
                d_match = re.search(r'(\d{4})[. -](\d{2})[. -](\d{2})', str(raw_date))
                if d_match:
                    formatted_date = f"{d_match.group(1)}-{d_match.group(2)}-{d_match.group(3)}"
            except: pass

        if src == '인스타그램':
            hashtags = ", ".join(re.findall(r'#(\w+)', item.get('본문내용', '')))
            kw_val = hashtags if hashtags else kw
        else:
            kw_val = kw

        unified_row = {
            "연번": i,                     # A열
            "플랫폼": src,                 # B열
            "작성일": formatted_date,       # C열
            "긍정/부정(감성분석)": item.get('감성분석', ''), # D열
            "분석 이유": reason,           # E열
            "본문 키워드": kw_val,         # F열
            "한줄 요약": sm,               # G열
            "URL": item.get('URL', '-')    # H열
        }
        unified_data.append(unified_row)
    
    res_df = pd.DataFrame(unified_data)
    # 최종 결과는 A~H열
    target_cols = ["연번", "플랫폼", "작성일", "긍정/부정(감성분석)", "분석 이유", "본문 키워드", "한줄 요약", "URL"]
    return res_df[target_cols]

def save_with_autofit(df, filepath, sheet_name='Sheet1'):
    """엑셀 저장 시 셀 너비를 내용에 맞춰 자동 조절"""
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter # 컬럼 문자 (A, B, C...)
            for cell in col:
                try:
                    # 한글 등 멀티바이트 문자 고려하여 길이 계산 (대략적)
                    val = str(cell.value) if cell.value is not None else ""
                    # 한글은 영문보다 자리를 더 차지하므로 보정
                    length = sum(2 if ord(c) > 128 else 1 for c in val)
                    if length > max_length:
                        max_length = length
                except: pass
            # 약간의 여백 추가 및 최대 너비 제한
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column].width = min(max(adjusted_width, 10), 80)

with st.sidebar:
    st.header("⚙️ 설정")
    
    # 설정값 (Streamlit Secrets 또는 환경 변수 우선 사용, 없을 시 기본값 사용)
    api_key = os.getenv("GEMINI_API_KEY", DEFAULT_API_KEY)
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except:
        pass
    
    # RESULT_DIR은 전역 DEFAULT_RESULT_DIR 사용 (필요 시 여기서 재정의)
    RESULT_DIR = DEFAULT_RESULT_DIR 
    os.makedirs(RESULT_DIR, exist_ok=True)
    use_sentiment = True
    insta_max_posts = 100 

    insta_id = "glick8745@gmail.com"
    insta_pw = "dlatl1964!"
    
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
    show_live_view = st.checkbox("📺 실시간 화면 보기", value=True, help="크롤링 중인 브라우저 화면을 하단에 작게 보여줍니다. (보기 전용)")
    is_headless = st.checkbox("🙈 브라우저 숨기기(Headless)", value=True, help="체크하면 브라우저 창이 보이지 않게 실행됩니다. 캡차(로봇 확인) 해결이 필요하면 체크를 해제하세요.")
    
    start_clicked = st.button("🚀 크롤링 시작", width="stretch")
    
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
                    width="stretch"
                )
            else:
                st.info("ℹ️ 결과가 [후기] 폴더에 저장되었습니다.")
        else:
            st.warning("⚠️ 수집된 결과가 없습니다.")

# 로그 및 결과 출력
col_log, col_res = st.columns([1, 2])

with col_log:
    st.subheader("📡 로그")
    log_placeholder = st.empty()

def update_logs(msg):
    st.session_state.logs.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    log_html = f"<div class='log-container'>{'<br>'.join(reversed(st.session_state.logs))}</div>"
    log_placeholder.markdown(log_html, unsafe_allow_html=True)

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
                    width="stretch"
                )
            else:
                st.info("ℹ️ 플랫폼별 개별 엑셀 파일은 `[후기]` 폴더에 저장되었습니다.")
        else:
            st.warning("⚠️ 수집된 결과가 없습니다. 옵션을 확인해 주세요.")

    live_view_placeholder = st.empty()
    if st.session_state.is_running:
        st.markdown("---")
        st.caption("📺 실시간 크롤링 화면 (Live View - 보기 전용)")
        if not is_headless:
            st.warning("⚠️ **직접 조작 안내**: 캡차 또는 로그인이 필요할 경우, 별도로 열린 **Chrome 브라우저 창**에서 직접 해결해 주세요.")

def update_ui():
    total = len(st.session_state.results)
    naver = len([r for r in st.session_state.results if r.get('출처') == '네이버 블로그'])
    daum = len([r for r in st.session_state.results if r.get('출처') == 'Daum 검색'])
    kakao = len([r for r in st.session_state.results if r.get('출처') == '카카오맵 리뷰'])
    google = len([r for r in st.session_state.results if r.get('출처') == '구글 리뷰'])
    insta = len([r for r in st.session_state.results if r.get('출처') == '인스타그램'])
    pos = len([r for r in st.session_state.results if r.get('감성분석') == '긍정'])
    
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
    res_list_placeholder.empty()

update_ui()

if start_clicked:
    st.session_state.results = []
    st.session_state.logs = []
    st.session_state.excel_data = None
    st.session_state.filename = None
    st.session_state.is_finished = False
    st.session_state.is_running = True
    
    try:
        update_logs("기존 브라우저 프로세스 정리 중...")
        try:
            kill_chrome_processes()
            time.sleep(1)
        except: pass
        
        # 1. 네이버 블로그 수집
        if do_naver:
            update_logs("네이버 블로그 수집 중...")
            try:
                naver_count = 0
                for item in crawl_naver_blog("한독의약박물관", 1, api_key, use_sentiment, use_summary, headless=is_headless):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                            continue
                        
                        is_rel, reason = is_relevant_by_keywords(item.get('본문내용', ''), item.get('제목', ''))
                        if not is_rel:
                            update_logs(f"⏩ [제외] {item.get('제목', '제목없음')[:15]}... ({reason})")
                            continue
                        if item.get('감성분석') == '부적합':
                            update_logs(f"⏩ [제외] {item.get('제목', '제목없음')[:15]}... (AI 판단: 관련 없음)")
                            continue
                        st.session_state.results.append(item)
                        naver_count += 1
                        update_ui()
                    else:
                        update_logs(item)
                if naver_count == 0:
                    update_logs("⚠ 네이버 블로그에서 최근 1주일간 검색된 결과가 없습니다. (필터링 기준을 확인하세요)")
                else:
                    update_logs(f"✅ 네이버 블로그 {naver_count}건 수집 완료!")
            except Exception as e:
                update_logs(f"네이버 오류: {e}")
                import traceback
                update_logs(traceback.format_exc())

        # 2. 다음 검색 수집
        if do_daum:
            update_logs("다음 검색 수집 중...")
            try:
                daum_count = 0
                for item in crawl_daum("한독의약박물관", 1, api_key, use_sentiment, use_summary, headless=is_headless):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                            continue
                        is_rel, reason = is_relevant_by_keywords(item.get('본문내용', ''), item.get('제목', ''))
                        if not is_rel:
                            update_logs(f"⏩ [제외] {item.get('제목', '제목없음')[:15]}... ({reason})")
                            continue
                        st.session_state.results.append(item)
                        daum_count += 1
                        update_ui()
                    else:
                        update_logs(item)
                update_logs(f"✅ 다음 검색 {daum_count}건 수집 완료!")
            except Exception as e:
                update_logs(f"다음 오류: {e}")

        # 3. 카카오맵 수집
        if do_kakao:
            update_logs("카카오맵 리뷰 수집 중...")
            try:
                kakao_count = 0
                for item in crawl_kakao_map(api_key, use_sentiment, use_summary, headless=is_headless):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                            continue
                        st.session_state.results.append(item)
                        kakao_count += 1
                        update_ui()
                    else:
                        update_logs(item)
                update_logs(f"✅ 카카오맵 리뷰 {kakao_count}건 수집 완료!")
            except Exception as e:
                update_logs(f"카카오맵 오류: {e}")

        # 4. 구글 리뷰 수집
        if do_google:
            update_logs("구글 지도 리뷰 수집 중...")
            try:
                google_count = 0
                for item in run_google_maps_crawler(api_key, use_sentiment, use_summary, headless=is_headless):
                    if isinstance(item, dict):
                        if item.get("type") == "screenshot":
                            if show_live_view:
                                live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                            continue
                        st.session_state.results.append(item)
                        google_count += 1
                        update_ui()
                    else:
                        update_logs(item)
                update_logs(f"✅ 구글 지도 리뷰 {google_count}건 수집 완료!")
            except Exception as e:
                update_logs(f"구글 오류: {e}")

        # 5. 인스타그램 수집
        if do_insta:
            update_logs("인스타그램 수집 시작...")
            is_cloud_env = sys.platform != 'win32'

            if is_cloud_env:
                # ── 클라우드 환경: 수집 불가 안내 ──────────────────────────────
                update_logs("⚠️ [인스타그램] 현재 클라우드(Streamlit Cloud) 환경에서는 인스타그램 수집이 불가합니다.")
                update_logs("💡 인스타그램 수집은 담당자 PC에서 로컬로 실행해 주세요.")
                st.warning(
                    "📵 **인스타그램 수집 불가 안내**\n\n"
                    "인스타그램은 클라우드 서버에서 실행 시 **봇 차단 정책**으로 인해 로그인이 불가능합니다.\n\n"
                    "**인스타그램 후기 수집 방법:**\n"
                    "1. 담당자 PC에 이 프로그램을 설치합니다.\n"
                    "2. `run_app.bat` 파일을 실행하여 로컬 환경에서 앱을 열고\n"
                    "3. '인스타그램' 항목만 체크한 뒤 수집을 진행합니다.\n\n"
                    "나머지 플랫폼(네이버, 다음, 카카오맵, 구글)은 이 페이지에서 정상적으로 수집됩니다."
                )
            else:
                # ── 로컬(Windows) 환경: 정상 수집 ────────────────────────────
                try:
                    driver, status = setup_chrome_driver(headless=is_headless, use_profile=True)
                    if not driver:
                        update_logs("❌ 브라우저를 시작할 수 없습니다.")
                    else:
                        login_gen = instagram_login(driver, insta_id, insta_pw)
                        login_success = False
                        
                        try:
                            while True:
                                try:
                                    item = next(login_gen)
                                    if isinstance(item, dict):
                                        if item.get("type") == "screenshot":
                                            if show_live_view:
                                                live_view_placeholder.image(item["data"], caption="인스타그램 로그인/인증 화면", width="stretch")
                                            continue
                                    else:
                                        update_logs(item)
                                except StopIteration as e:
                                    login_success = e.value
                                    break
                        except Exception as le:
                            update_logs(f"⚠️ 로그인 시도 중 오류: {le}")
                            login_success = False

                        if login_success:
                            insta_count = 0
                            # 5-1. 해시태그 수집 (#한독의약박물관)
                            update_logs("📸 해시태그(#한독의약박물관) 수집 중...")
                            for item in crawl_hashtag(driver, "한독의약박물관", insta_max_posts, api_key, use_sentiment, use_summary):
                                if isinstance(item, dict):
                                    if item.get("type") == "screenshot":
                                        if show_live_view:
                                            live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                                        continue
                                    if not any(r.get('URL') == item.get('URL') for r in st.session_state.results):
                                        st.session_state.results.append(item)
                                        insta_count += 1
                                        update_ui()
                                else:
                                    update_logs(item)
                            
                            # 5-2. 공식 계정(@handokmuseum) 태그됨 수집
                            update_logs("🏷️ 공식 계정(@handokmuseum) '태그됨' 수집 중...")
                            for item in crawl_tagged_posts(driver, "handokmuseum", insta_max_posts, api_key, use_sentiment, use_summary):
                                if isinstance(item, dict):
                                    if item.get("type") == "screenshot":
                                        if show_live_view:
                                            live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                                        continue
                                    if not any(r.get('URL') == item.get('URL') for r in st.session_state.results):
                                        st.session_state.results.append(item)
                                        insta_count += 1
                                        update_ui()
                                else:
                                    update_logs(item)

                            # 5-3. 장소 수집 (한독의약박물관 Location ID)
                            update_logs("📍 장소(Location) 기반 수집 중...")
                            for item in crawl_location(driver, "109120676658159", insta_max_posts, api_key, use_sentiment, use_summary):
                                if isinstance(item, dict):
                                    if item.get("type") == "screenshot":
                                        if show_live_view:
                                            live_view_placeholder.image(item["data"], caption="현재 수집 중인 화면", width="stretch")
                                        continue
                                    if not any(r.get('URL') == item.get('URL') for r in st.session_state.results):
                                        st.session_state.results.append(item)
                                        insta_count += 1
                                        update_ui()
                                else:
                                    update_logs(item)

                            update_logs(f"✅ 인스타그램 {insta_count}건 수집 완료!")
                        driver.quit()
                except Exception as e:
                    update_logs(f"인스타그램 오류: {e}")

        # 6. 결과 저장
        if st.session_state.results:
            update_logs("💾 결과 파일 저장 중...")
            try:
                df = pd.DataFrame(st.session_state.results)
                today = datetime.datetime.now().strftime("%Y%m%d")
                target_dir = os.path.join(RESULT_DIR, f"[Data_{today}]")
                os.makedirs(target_dir, exist_ok=True)
                
                # 플랫폼별 저장
                platforms = list(set([r.get('출처', '') for r in st.session_state.results if r.get('출처')]))
                for src in platforms:
                    sdf = df[df['출처'] == src]
                    if not sdf.empty:
                        pdf = process_for_excel(sdf, src)
                        fname = f"{src}_{today}.xlsx"
                        save_with_autofit(pdf, os.path.join(target_dir, fname), sheet_name=src)
                
                # 통합 보고서 저장
                unified_df = process_for_unified_excel(df)
                positive_df = unified_df[unified_df["긍정/부정(감성분석)"] == "긍정"].copy()
                positive_df["연번"] = range(1, len(positive_df) + 1) # 연번 재정렬
                
                negative_df = unified_df[unified_df["긍정/부정(감성분석)"] == "부정"].copy()
                negative_df["연번"] = range(1, len(negative_df) + 1) # 연번 재정렬
                
                unified_fname = f"{today}_한독의약박물관 관람 후기.xlsx"
                unified_filepath = os.path.join(target_dir, unified_fname)
                
                # 여러 시트 및 너비 조절 저장용 헬퍼
                def save_multi_sheets(file_dest, df_list, sheet_names):
                    with pd.ExcelWriter(file_dest, engine='openpyxl') as writer:
                        for d, s in zip(df_list, sheet_names):
                            d.to_excel(writer, index=False, sheet_name=s)
                            ws = writer.sheets[s]
                            for col in ws.columns:
                                max_len = 0
                                column = col[0].column_letter
                                for cell in col:
                                    val = str(cell.value) if cell.value is not None else ""
                                    length = sum(2 if ord(c) > 128 else 1 for c in val)
                                    if length > max_len: max_len = length
                                ws.column_dimensions[column].width = min(max(max_len + 2, 10), 80)
                    return True

                save_multi_sheets(unified_filepath, [unified_df, positive_df, negative_df], ['전체 후기', '긍정 후기', '부정 후기'])
                
                # 다운로드 버튼용
                output = io.BytesIO()
                save_multi_sheets(output, [unified_df, positive_df, negative_df], ['전체 후기', '긍정 후기', '부정 후기'])
                
                st.session_state.excel_data = output.getvalue()
                st.session_state.filename = unified_fname
                update_logs(f"✅ 저장 완료: {target_dir}")
            except Exception as e:
                update_logs(f"⚠️ 파일 저장 오류: {e}")
                
    finally:
        st.session_state.is_finished = True
        st.session_state.is_running = False
        update_logs("🏁 모든 작업 완료!")
        st.rerun()
