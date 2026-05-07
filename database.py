import os
import time
import requests
import urllib.parse
from datetime import datetime
import pytz
from dotenv import load_dotenv
import streamlit as st

# .env 파일 로드 (로컬 개발 환경용)
load_dotenv()

# 한국 표준시(KST) 타임존 설정
KST = pytz.timezone('Asia/Seoul')

def get_kst_now():
    """현재 시각을 KST로 반환 (timezone-naive)"""
    return datetime.now(KST).replace(tzinfo=None)

@st.cache_resource
def get_supabase_config():
    """Supabase 접속 정보 및 헤더 반환"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        
    if not url or not key:
        st.error("Supabase 설정이 누락되었습니다. secrets.toml 혹은 환경변수를 확인하세요.")
        
    base_url = url.rstrip('/') + "/rest/v1"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    return base_url, headers

# --- [수행평가 전용 신규 함수] ---

def get_student_info(student_id: str, password: str):
    """학번과 비밀번호로 학생 정보를 확인하고 반(class_name) 정보를 가져옴"""
    base_url, headers = get_supabase_config()
    s_id = urllib.parse.quote(student_id)
    pw = urllib.parse.quote(password)
    
    url = f"{base_url}/students?select=*&student_id=eq.{s_id}&password=eq.{pw}"
    resp = requests.get(url, headers=headers, verify=False)
    
    if resp.status_code == 200:
        data = resp.json()
        return data[0] if data else None
    return None

def get_scenario_by_class_and_theme(class_name: str, theme: str):
    """학생의 학급과 선택한 테마에 매칭되는 시나리오를 가져옴 (반별 유출 방지)"""
    base_url, headers = get_supabase_config()
    c_name = urllib.parse.quote(class_name)
    t_name = urllib.parse.quote(theme)
    
    url = f"{base_url}/scenarios?select=*&class_name=eq.{c_name}&theme=eq.{t_name}"
    resp = requests.get(url, headers=headers, verify=False)
    
    if resp.status_code == 200:
        data = resp.json()
        # 해당 학급/테마 조합에 여러 시나리오가 있을 경우 첫 번째 것을 반환
        return data[0] if data else None
    return None

def check_already_submitted(student_id: str):
    """해당 학생이 이미 제출했는지 확인 (중복 제출 방지 및 결과 확인용)"""
    base_url, headers = get_supabase_config()
    s_id = urllib.parse.quote(student_id)
    
    url = f"{base_url}/submissions?select=*&student_id=eq.{s_id}"
    resp = requests.get(url, headers=headers, verify=False)
    
    if resp.status_code == 200:
        data = resp.json()
        if len(data) > 0:
            return data[0]
    return None

def save_performance_submission(student_id, scenario_id, answers, result):
    """수행평가 답안 및 AI 채점 결과를 DB에 저장"""
    base_url, headers = get_supabase_config()
    
    # 루브릭 점수 계산 (True 개수 합산)
    satisfied_count = sum([result[k] for k in result if k.startswith('is_')])
    
    # 루브릭 점수 매핑 (2.5점 단위)
    score_map = {6: 20.0, 5: 17.5, 4: 15.0, 3: 12.5, 2: 10.0, 1: 7.5, 0: 5.0}
    final_score = score_map.get(satisfied_count, 5.0)
    
    # 피드백과 점수 분리 (Scores 칼럼 중복 저장 방지)
    # result 딕셔너리를 복사하여 원본 훼손을 막습니다.
    scores_only = result.copy()
    ai_feedback = scores_only.pop("ai_feedback", "")
    
    payload = {
        "student_id": student_id,
        "scenario_id": scenario_id,
        "answers": answers, # JSON 형식 (det1, cor1, ...)
        "scores": scores_only,   # JSON 형식 (is_det_1_ok, ... 등 1~6번 항목만)
        "satisfied_count": satisfied_count,
        "final_score": final_score,
        "ai_feedback": ai_feedback,
        "submitted_at": get_kst_now().isoformat()
    }
    
    post_headers = headers.copy()
    post_headers["Prefer"] = "return=representation"
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(f"{base_url}/submissions", headers=post_headers, json=payload, verify=False, timeout=10)
            if resp.status_code in (200, 201):
                return payload
            else:
                if attempt < max_retries - 1:
                    time.sleep(1.5)
                    continue
                st.error(f"제출 데이터 저장 중 오류가 발생했습니다: {resp.text}")
                return None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.5)
                continue
            st.error(f"네트워크 오류로 서버 접속에 실패했습니다: {str(e)}")
            return None

# --- [기존 기능 유지용 - 필요 시 활성화] ---

def get_student_device(student_id: str):
    """기존 기기 제한 로직 호환용"""
    base_url, headers = get_supabase_config()
    s_id = urllib.parse.quote(student_id)
    resp = requests.get(f"{base_url}/student_devices?select=device_id&student_id=eq.{s_id}", headers=headers, verify=False)
    if resp.status_code == 200:
        data = resp.json()
        return data[0]["device_id"] if data else None
    return None

def register_student_device(student_id: str, device_id: str):
    base_url, headers = get_supabase_config()
    data = {"student_id": student_id, "device_id": device_id}
    requests.post(f"{base_url}/student_devices", headers=headers, json=data, verify=False)

def log_blocked_attempt(student_id: str, attempted_device_id: str):
    base_url, headers = get_supabase_config()
    data = {"student_id": student_id, "attempted_device_id": attempted_device_id}
    requests.post(f"{base_url}/blocked_logins", headers=headers, json=data, verify=False)