import os
import requests
import urllib.parse
from datetime import datetime
import pytz
from dotenv import load_dotenv
import streamlit as st
import pandas as pd

# .env 파일 로드 (로컬 개발 환경)
load_dotenv()

# 한국 표준시(KST) 타임존 설정
KST = pytz.timezone('Asia/Seoul')

def get_kst_now():
    """현재 시각을 KST로 반환 (timezone-naive)"""
    return datetime.now(KST).replace(tzinfo=None)

@st.cache_resource
def get_supabase_config():
    """Supabase 접속 정보 반환"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except KeyError:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        
    if not url or not key:
        st.error("Supabase URL 혹은 Key를 불러오지 못했습니다. .streamlit/secrets.toml 을 확인하세요.")
        
    base_url = url.rstrip('/') + "/rest/v1"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    return base_url, headers

class ConvWrapper:
    """기존 dot notation 호환용 래퍼 클래스"""
    def __init__(self, data):
        self.__dict__.update(data)
        if 'created_at' in data:
            try:
                # timezone 처리
                ts = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
                # KST로 변환
                self.timestamp = ts.astimezone(KST).replace(tzinfo=None)
            except:
                self.timestamp = datetime.now()
        else:
            self.timestamp = datetime.now()

def save_conversation_to_db(student_id: str, device_id: str, question: str, answer: str, 
                            content_element: str = None):
    """대화 데이터를 데이터베이스에 저장"""
    base_url, headers = get_supabase_config()
    data = {
        "student_id": student_id,
        "device_id": device_id,
        "question": question,
        "answer": answer,
        "content_element": content_element
    }
    
    post_headers = headers.copy()
    post_headers["Prefer"] = "return=representation"
    
    resp = requests.post(f"{base_url}/conversations", headers=post_headers, json=data)
    if resp.status_code in (200, 201):
        res_data = resp.json()
        return res_data[0]["id"] if res_data else None
    else:
        error_msg = f"Supabase Insert Error: {resp.text}"
        st.error(error_msg)
        raise Exception(error_msg)

def get_all_conversations():
    """모든 대화 데이터 조회"""
    base_url, headers = get_supabase_config()
    resp = requests.get(f"{base_url}/conversations?select=*&order=created_at.desc", headers=headers)
    if resp.status_code == 200:
        return [ConvWrapper(d) for d in resp.json()]
    return []

def get_conversations_by_student(student_id: str):
    """특정 학생의 대화 데이터 조회"""
    base_url, headers = get_supabase_config()
    s_id = urllib.parse.quote(student_id)
    resp = requests.get(f"{base_url}/conversations?select=*&student_id=eq.{s_id}&order=created_at.desc", headers=headers)
    if resp.status_code == 200:
        return [ConvWrapper(d) for d in resp.json()]
    return []

def get_statistics():
    """전체 통계 조회 (간소화)"""
    base_url, headers = get_supabase_config()
    
    # 1. 문서 총 갯수 구하기
    cnt_headers = headers.copy()
    cnt_headers["Prefer"] = "count=exact"
    resp = requests.get(f"{base_url}/conversations?select=id", headers=cnt_headers)
    total_conversations = 0
    if resp.status_code == 200 or resp.status_code == 206:
        crange = resp.headers.get("Content-Range", "")
        if crange and "/" in crange:
            try:
                total_conversations = int(crange.split("/")[-1])
            except ValueError:
                total_conversations = len(resp.json())
        else:
            total_conversations = len(resp.json())
            
    # 2. 학생 수 고유값 구하기
    resp2 = requests.get(f"{base_url}/conversations?select=student_id", headers=headers)
    total_students = 0
    if resp2.status_code == 200:
        data = resp2.json()
        if data:
            df = pd.DataFrame(data)
            total_students = df['student_id'].nunique()
            
    return {
        'total_conversations': total_conversations,
        'total_students': total_students,
        'avg_per_student': round(total_conversations / total_students, 1) if total_students > 0 else 0
    }

def get_content_element_distribution():
    """성취기준(content_element)별 질문 분포"""
    base_url, headers = get_supabase_config()
    resp = requests.get(f"{base_url}/conversations?select=content_element", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        if not data:
            return []
        df = pd.DataFrame(data)
        if 'content_element' not in df or df.empty:
            return []
        
        df_clean = df.dropna(subset=['content_element'])
        df_clean = df_clean[df_clean['content_element'] != 'N/A']
        counts = df_clean['content_element'].value_counts()
        return [(index, count) for index, count in counts.items()]
    return []

def get_student_question_counts():
    """학생별 질문 횟수"""
    base_url, headers = get_supabase_config()
    resp = requests.get(f"{base_url}/conversations?select=student_id", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        if not data:
            return []
        df = pd.DataFrame(data)
        if 'student_id' not in df or df.empty:
            return []
        counts = df['student_id'].value_counts()
        return [(index, count) for index, count in counts.items()]
    return []

# --- 연구용/기기 제한용 추가 함수 ---

def get_student_device(student_id: str):
    """학생에게 할당된 기기 조회"""
    base_url, headers = get_supabase_config()
    s_id = urllib.parse.quote(student_id)
    resp = requests.get(f"{base_url}/student_devices?select=device_id&student_id=eq.{s_id}", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        if data:
            return data[0]["device_id"]
    return None

def register_student_device(student_id: str, device_id: str):
    """최초 로그인 학생의 기기 등록"""
    base_url, headers = get_supabase_config()
    data = {"student_id": student_id, "device_id": device_id}
    requests.post(f"{base_url}/student_devices", headers=headers, json=data)

def log_blocked_attempt(student_id: str, attempted_device_id: str):
    """차단된 로그인 시도 기록"""
    base_url, headers = get_supabase_config()
    data = {"student_id": student_id, "attempted_device_id": attempted_device_id}
    requests.post(f"{base_url}/blocked_logins", headers=headers, json=data)

