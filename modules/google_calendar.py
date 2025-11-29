# google_calendar.py

import os
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta # 🌟 timedelta 사용
from pytz import timezone               # 🌟 시간대 처리를 위해 pytz 사용

# 읽기 전용 권한
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

CREDENTIALS_FILE = 'credentials.json'  # Google Cloud에서 다운받은 OAuth 파일
TOKEN_FILE = 'token.pkl'  # 인증 토큰 저장

def authenticate_google():
    creds = None
    # 기존 토큰 불러오기
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    # 토큰 없거나 만료되었으면 새로 로그인 또는 갱신
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    return creds

def fetch_events(max_results=200): # 최대 결과 수를 200개로 넉넉하게 설정
    creds = authenticate_google()
    service = build('calendar', 'v3', credentials=creds)
    
    # 🌟 현재 시각과 14일 후 시각 계산
    KST = timezone('Asia/Seoul')
    
    # timeMin: 현재 시각 (한국 시간 기준)
    now_kst = datetime.now(KST)
    time_min = now_kst.isoformat()
    
    # timeMax: 현재 시각으로부터 14일 후 시각 (2주)
    next_two_weeks_kst = now_kst + timedelta(days=14) # 🌟 14일로 설정
    time_max = next_two_weeks_kst.isoformat()

    events_result = service.events().list(
        calendarId='primary', 
        maxResults=max_results,        
        singleEvents=True,
        orderBy='startTime',
        timeMin=time_min,              # 현재 시각 이후 이벤트만 가져옴
        timeMax=time_max               # 14일 후 시각 이전 이벤트만 가져옴
    ).execute()
    
    events = events_result.get('items', [])
    # 시작 시간, 제목만 추출
    event_list = []
    for e in events:
        start = e['start'].get('dateTime', e['start'].get('date'))
        summary = e.get('summary', '제목 없음')
        event_list.append({'start': start, 'summary': summary})
    return event_list