import streamlit as st
import pandas as pd
import uuid
import json
from streamlit_javascript import st_javascript

# 기존 파일들에서 필요한 함수 임포트
from database import (
    get_supabase_config,
    get_kst_now,
    # 아래 함수들은 신규 프로젝트에 맞춰 database.py에 추가되어야 합니다.
    get_student_info, 
    get_scenario_by_class_and_theme,
    save_performance_submission,
    check_already_submitted
)
from gemini import grade_performance_task # 채점 전용으로 새로 만들 파일

# 페이지 설정
st.set_page_config(page_title="화학 평형 AI 오류 정정 수행평가", page_icon="🧪", layout="wide")

# --- 기기 보안 로직 (기존 활용) ---
if "browser_device_id" not in st.session_state:
    js_code = "(function() { var dev = localStorage.getItem('device_id'); return dev ? dev : 'NONE'; })()"
    dev_id = st_javascript(js_code)
    if dev_id == 0: st.stop()
    elif dev_id == 'NONE':
        new_uuid = str(uuid.uuid4())
        st_javascript(f"localStorage.setItem('device_id', '{new_uuid}');")
        st.session_state.browser_device_id = new_uuid
        st.rerun()
    else:
        st.session_state.browser_device_id = dev_id

# --- 로그인 처리 ---
def handle_login():
    with st.sidebar:
        st.header("🔐 학생 로그인")
        if not st.session_state.get("authenticated"):
            s_id = st.text_input("학번 (5자리)", placeholder="예: 20101")
            pw = st.text_input("비밀번호 (6자리)", type="password")
            
            if st.button("평가 접속", use_container_width=True, type="primary"):
                user = get_student_info(s_id, pw) # DB에서 학번/비번/반 정보 가져옴
                if user:
                    st.session_state.authenticated = True
                    st.session_state.student_id = s_id
                    st.session_state.student_name = user['name']
                    st.session_state.class_name = user['class_name']
                    st.rerun()
                else:
                    st.error("학번 또는 비밀번호가 올바르지 않습니다.")
        else:
            st.success(f"✅ {st.session_state.student_name} 학생")
            st.caption(f"소속: {st.session_state.class_name} / {st.session_state.student_id}")
            if st.button("로그아웃"):
                st.session_state.clear()
                st.rerun()

# --- 수행평가 메인 화면 ---
def performance_mode():
    st.title("🧪 화학 평형 AI 리포트 오류 정정")
    st.info(f"👋 반갑습니다, {st.session_state.student_name} 학생. 본인의 학급({st.session_state.class_name})에 맞는 시나리오가 자동으로 할당됩니다.")
    
    # 1. 테마 선택
    themes = ["청정에너지", "첨단 신소재", "보건 및 생명", "반도체 공정", "대규모 공정 (산업)"]
    selected_theme = st.selectbox("탐구할 화학 평형 테마를 선택하세요", ["선택하세요"] + themes)

    if selected_theme == "선택하세요":
        st.warning("👈 위에서 테마를 선택하면 AI 리포트가 나타납니다.")
        return

    # 2. 시나리오 불러오기
    if "current_scenario" not in st.session_state or st.session_state.get("last_theme") != selected_theme:
        scenario = get_scenario_by_class_and_theme(st.session_state.class_name, selected_theme)
        if scenario:
            st.session_state.current_scenario = scenario
            st.session_state.last_theme = selected_theme
        else:
            st.error("해당 테마의 시나리오를 불러올 수 없습니다. 선생님께 문의하세요.")
            return

    scenario = st.session_state.current_scenario
    
    # 중복 제출 확인
    already_done_data = check_already_submitted(st.session_state.student_id)
    if already_done_data:
        st.session_state.submitted = True
        st.session_state.submission_data = already_done_data
        st.rerun()

    # 3. 리포트 출력
    st.divider()
    st.subheader(f"📄 [AI 리포트] {scenario['title']}")
    with st.container(border=True):
        content_text = scenario['content']
        import re
        content_text = re.sub(r'\[MOL:.*?\]', '', content_text)
        
        # 줄바꿈을 <br>로 변경하여 확실한 단락 분리
        content_text = content_text.replace('\n', '<br>')
        
        # 1. 반응식 한 줄 띄우고 가운데 정렬
        content_text = re.sub(r'((?:주요 |화학 )?반응식:.*?)(?=<br>|$)', r'<br><div style="text-align: center; font-size: 1.1em; font-weight: bold; margin: 20px 0; color: #1E3A8A;">\1</div><br>', content_text)
        
        # 2. 단락 1, 2, 3 줄바꿈 처리 및 강조
        content_text = re.sub(r'(<br>)(단락 \d+.*?:)', r'\1<br><b>\2</b>', content_text)
        
        # 3. 지수 표현 윗첨자 (예: 10^12 -> 10<sup>12</sup>)
        content_text = re.sub(r'\^(-?\d+)', r'<sup>\1</sup>', content_text)
        
        st.markdown(content_text, unsafe_allow_html=True)

    st.divider()

    # 4. 답안 작성 폼
    st.subheader("📝 오류 수정 답안지")
    st.caption("AI의 답변 중 학문적 오류를 찾아 파악 내용과 교정 내용을 구체적으로 서술하세요.")
    
    with st.form("evaluation_form"):
        # 3가지 답변 영역을 탭으로 구분하여 깔끔하게 배치
        ans_tab1, ans_tab2, ans_tab3 = st.tabs(["[답변 1] 농도 관련", "[답변 2] 압력 관련", "[답변 3] 온도 관련"])
        
        with ans_tab1:
            det1 = st.text_area("오류 파악: 왜 틀렸나요?", height=100, key="d1")
            cor1 = st.text_area("정정 내용: 바르게 고치면 무엇인가요?", height=100, key="c1")
        
        with ans_tab2:
            det2 = st.text_area("오류 파악: 왜 틀렸나요?", height=100, key="d2")
            cor2 = st.text_area("정정 내용: 바르게 고치면 무엇인가요?", height=100, key="c2")
            
        with ans_tab3:
            det3 = st.text_area("오류 파악: 왜 틀렸나요?", height=100, key="d3")
            cor3 = st.text_area("정정 내용: 바르게 고치면 무엇인가요?", height=100, key="c3")

        submitted = st.form_submit_button("최종 제출 및 AI 즉시 채점", type="primary", use_container_width=True)

        if submitted:
            if not all([det1, cor1, det2, cor2, det3, cor3]):
                st.error("⚠️ 모든 항목을 작성해야 제출할 수 있습니다.")
            else:
                with st.spinner("AI가 선생님의 루브릭에 따라 채점 중입니다..."):
                    # 5. Gemini 채점 로직 호출
                    student_answers = {"det1": det1, "cor1": cor1, "det2": det2, "cor2": cor2, "det3": det3, "cor3": cor3}
                    grading_result = grade_performance_task(scenario, student_answers)
                    
                    # 6. 결과 저장
                    saved_data = save_performance_submission(
                        student_id=st.session_state.student_id,
                        scenario_id=scenario.get('id', scenario.get('scenario_no')),
                        answers=student_answers,
                        result=grading_result
                    )
                    
                    if saved_data:
                        st.session_state.submitted = True
                        st.session_state.submission_data = saved_data
                        st.rerun()

# --- 결과 페이지 ---
def show_result():
    st.balloons()
    st.header("✅ 제출 완료!")
    st.success("수행평가 답안이 정상적으로 제출 및 채점되었습니다.")
    
    sub = st.session_state.get("submission_data")
    # if sub:
    #     st.divider()
    #     st.subheader("📊 AI 채점 결과 요약")
    #     st.metric("최종 점수", f"{sub.get('final_score')} / 20.0 점")
    #     
    #     st.markdown("### 👩‍🏫 선생님(AI) 피드백")
    #     st.info(sub.get('ai_feedback'))
    #     
    #     st.markdown("### 📝 세부 평가 내역")
    #     scores = sub.get('scores', {})
    #     cols = st.columns(3)
    #     with cols[0]:
    #         st.write("**[1. 농도]**")
    #         st.caption(f"파악: {'✅' if scores.get('is_det_1_ok') else '❌'}")
    #         st.caption(f"교정: {'✅' if scores.get('is_cor_1_ok') else '❌'}")
    #     with cols[1]:
    #         st.write("**[2. 압력]**")
    #         st.caption(f"파악: {'✅' if scores.get('is_det_2_ok') else '❌'}")
    #         st.caption(f"교정: {'✅' if scores.get('is_cor_2_ok') else '❌'}")
    #     with cols[2]:
    #         st.write("**[3. 온도]**")
    #         st.caption(f"파악: {'✅' if scores.get('is_det_3_ok') else '❌'}")
    #         st.caption(f"교정: {'✅' if scores.get('is_cor_3_ok') else '❌'}")

    st.info("실제 선생님의 최종 확인 후 생활기록부에 반영될 예정입니다. 수고하셨습니다!")
    if st.button("처음으로 돌아가기"):
        st.session_state.submitted = False
        st.session_state.submission_data = None
        st.rerun()

# --- 메인 실행 ---
handle_login()

if st.session_state.get("authenticated"):
    if st.session_state.get("submitted"):
        show_result()
    else:
        performance_mode()
else:
    st.title("🧪 화학 평형 AI 오류 정정 수행평가")
    st.markdown("---")
    st.markdown("### 👈 왼쪽 사이드바에서 로그인하세요")
    st.info("선생님이 배부하신 학번과 비밀번호를 입력해 주세요.")