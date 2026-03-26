import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os

# ========================================================
# 발신자 이메일 계정 정보 설정
# (구글 계정의 경우, 로그인 비밀번호가 아닌 '앱 비밀번호(16자리)'가 필요합니다.)
# ========================================================
# 주의: 아래 큰따옴표 안에 본인 구글 이메일과 발급받은 16자리 앱 비밀번호(띄어쓰기 없이)를 적어주세요!
# (예: SENDER_EMAIL = "glick8745@gmail.com")
SENDER_EMAIL = "SeonYeong.Lee@handok.com"
SENDER_APP_PASSWORD = "pass123!"

# ========================================================
# 리포트를 받을 수신자 이메일 (여러 명일 경우 계속 추가 가능)
# ========================================================
RECEIVER_EMAILS = [
    "museum@handok.com"
]

def send_report_email(filepath):
    if not SENDER_EMAIL:
        print("[이메일 자동발송] 발신자 이메일(SENDER_EMAIL) 설정이 없어 메일 발송을 생략합니다.")
        return False
        
    if not RECEIVER_EMAILS:
        print("[이메일 자동발송] 수신자 이메일(RECEIVER_EMAILS) 설정이 없어 메일 발송을 생략합니다.")
        return False
        
    print(f"\n[이메일 자동발송] {SENDER_EMAIL} 계정으로 결과 엑셀 파일 발송을 시도합니다...")
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(RECEIVER_EMAILS)
    msg['Subject'] = "[자동보고] 한독의약박물관 관람 후기 수집 결과 리포트"
    
    body = f"""
안녕하세요,

지정된 스케줄러에 따라 한독의약박물관(네이버 블로그, 구글 맵스 리뷰, 인스타그램) 최신 관람 후기를 수집하였습니다.
감성 분석이 포함된 전체 결과는 첨부된 엑셀 파일을 확인해 주시기 바랍니다.

- 파일명: {os.path.basename(filepath)}
- 본 메일은 파이썬 자동화 봇에 의해 자동으로 발송되었습니다.
"""
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    if os.path.exists(filepath):
        try:
            with open(filepath, "rb") as f:
                attachment = MIMEApplication(f.read(), _subtype="xlsx")
                attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(filepath))
                msg.attach(attachment)
        except Exception as e:
            print(f"[이메일 자동발송] 파일 첨부 중 오류: {e}")
            return False
    else:
        print("[이메일 자동발송] 첨부할 엑셀 파일을 찾을 수 없습니다.")
        return False
        
    try:
        if "@handok.com" in SENDER_EMAIL.lower():
            # 사내 이메일망 전용 릴레이 서버 사용 (앱 비밀번호 불필요)
            server = smtplib.SMTP('hdpsmxv01.handok.com', 25)
            server.send_message(msg)
            server.quit()
        else:
            # 기타 Gmail 서버 (보안 연결 TLS)
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            if SENDER_APP_PASSWORD:
                server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.send_message(msg)
            server.quit()
            
        print(f"[이메일 발송 성공] 보고서가 수신자({len(RECEIVER_EMAILS)}명)에게 안전하게 발송되었습니다!")
        return True
    except Exception as e:
        print(f"[이메일 발송 오류] 메일 서버 접속에 실패했습니다: {e}")
        return False
