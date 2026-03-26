import os
import glob
from mail_utils import send_report_email

# [후기] 폴더에서 가장 최근의 xlsx 파일 찾기
result_dir = r"C:\Users\kr2200047\Documents\한독의약박물관 관람 후기 자동 수집\[후기]"
list_of_files = glob.glob(f"{result_dir}\\*.xlsx")
if not list_of_files:
    print("엑셀 파일이 존재하지 않습니다.")
else:
    latest_file = max(list_of_files, key=os.path.getctime)
    print(f"가장 최근 엑셀 파일: {latest_file}")
    
    # 메일 발송 테스트
    success = send_report_email(latest_file)
    if success:
        print("메일 발송 테스트 성공!")
    else:
        print("메일 발송 테스트 실패.")
