import streamlit as st
import pandas as pd
import re
import uuid
from datetime import datetime
import pytz
import json
import plotly.express as px
import plotly.graph_objects as go
from streamlit_javascript import st_javascript
from user_db import USER_DB

# 데이터베이스 관련 임포트 (간소화)
from database import (
    get_supabase_config,
    save_conversation_to_db,
    get_all_conversations,
    get_conversations_by_student,
    get_statistics,
    get_content_element_distribution,
    get_student_question_counts,
    get_kst_now,
    get_student_device,
    register_student_device,
    log_blocked_attempt,
)

# Gemini AI 관련 임포트 (간소화)
from gemini import chat_with_chemistry_tutor

# 분자 시각화 관련 임포트
from mol_viewer import (
    parse_mol_tags, remove_mol_tags, render_molecule_png,
    parse_lewis_tags, remove_all_vis_tags, render_lewis_png,
    generate_3dmol_html,
)


SUBSCRIPT_MAP = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')

def convert_chemical_subscripts(text: str) -> str:
    formula_pattern = r'(?<!\[)([A-Z][a-z]?)(\d+)([A-Z][a-z]?(?:\d+))*(?![^\[]*\])'

    def replace_digits_in_formula(match):
        full = match.group(0)
        return re.sub(r'(\d+)', lambda m: m.group(0).translate(SUBSCRIPT_MAP), full)

    result = re.sub(formula_pattern, replace_digits_in_formula, text)
    return result


def display_mol_cards(mol_data_list: list):
    for mol_data in mol_data_list:
        html_3d = generate_3dmol_html(
            mol_data['smiles'],
            angle=mol_data['angle'],
            shape=mol_data['shape']
        )
        if html_3d:
            import streamlit.components.v1 as components
            components.html(html_3d, height=420, scrolling=False)
        else:
            png_bytes = render_molecule_png(mol_data['smiles'])
            if png_bytes:
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(png_bytes, use_container_width=True)
                with col_info:
                    st.markdown(f"**분자 구조 정보**")
                    st.markdown(f"- **결합각**: {mol_data['angle']}")
                    st.markdown(f"- **분자 기하 구조**: {mol_data['shape']}")


def display_lewis_cards(smiles_list: list):
    for smiles in smiles_list:
        png_bytes = render_lewis_png(smiles)
        if png_bytes:
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(png_bytes, use_container_width=True)
            with col_info:
                st.markdown(f"**루이스 전자점식**")
                st.markdown(f"- 비공유 전자쌍을 점(··)으로 표시")
                st.markdown(f"- 공유 결합을 선(—)으로 표시")


def display_assistant_message(content: str):
    mol_tags = parse_mol_tags(content)
    lewis_tags = parse_lewis_tags(content)
    clean_text = remove_all_vis_tags(content)
    clean_text = convert_chemical_subscripts(clean_text)
    st.markdown(clean_text)
    if lewis_tags:
        display_lewis_cards(lewis_tags)
    if mol_tags:
        display_mol_cards(mol_tags)


def parse_tag_from_response(response: str) -> tuple:
    """
    AI 응답에서 [TAG: ...] 부분을 추출하고, 클린 텍스트와 태그를 반환합니다.
    (스캐폴딩 레벨 정보는 제거하고 성취기준/내용요소만 반환)
    """
    tag_pattern = r'\[TAG:\s*([^\n]+)\]\s*$'
    match = re.search(tag_pattern, response, re.MULTILINE)
    
    if match:
        tag_content = match.group(1).strip()
        parts = [p.strip() for p in tag_content.split('|')]
        # 첫 2개 요소(보통 성취기준, 내용요소)만 결합
        if len(parts) >= 2:
            content_element = f"{parts[0]} | {parts[1]}"
        else:
            content_element = tag_content
            
        clean_response = response[:match.start()].strip()
        return clean_response, content_element
    
    return response.strip(), 'N/A'


# 페이지 설정
st.set_page_config(page_title="화학 AI 튜터 연구 플랫폼", page_icon="🧪", layout="wide")

# 데이터베이스 연결 확인
try:
    get_supabase_config()
except Exception as e:
    st.error(f"데이터베이스 연결 오류: {e}")


def handle_login_sidebar():
    """사이드바 로그인/로그아웃 처리"""
    with st.sidebar:
        st.header("🔐 로그인")
        if st.session_state.get("pw_authenticated"):
            st.success(f"✅ {st.session_state.get('student_name', '')} 님")
            st.caption(f"ID: {st.session_state.get('student_id', '')}")
            st.markdown("---")
            if st.button("로그아웃", key="sidebar_logout_btn", use_container_width=True):
                for key in ["pw_authenticated", "student_id", "student_name",
                            "messages", "conversation_ids"]:
                    st.session_state.pop(key, None)
                st.rerun()
        else:
            st.markdown("이름과 비밀번호를 입력하세요.")
            name_input = st.text_input("이름", key="login_name_input",
                                       placeholder="예) 홍길동")
            pw_input = st.text_input("비밀번호 (6자리)", type="password",
                                     key="login_pw_input", max_chars=6,
                                     placeholder="6자리 숫자")
            if st.button("로그인", type="primary", key="sidebar_login_btn",
                         use_container_width=True):
                if name_input in USER_DB and USER_DB[name_input] == pw_input:
                    # 기기 제한 로직 검증
                    dev_id = st.session_state.get('browser_device_id')
                    if not dev_id:
                        st.error("기기 정보를 불러오는 중입니다. 잠시 후 다시 시도해주세요.")
                        return

                    db_dev_id = get_student_device(name_input)
                    if not db_dev_id:
                        # 최초 로그인 시 현재 기기 등록
                        register_student_device(name_input, dev_id)
                    elif db_dev_id != dev_id:
                        # 다른 기기에서 접속 시도 차단
                        log_blocked_attempt(name_input, dev_id)
                        st.error("⚠️ 다른 기기에서 이미 접속된 계정입니다. 접속이 차단되었습니다.")
                        return

                    st.session_state.pw_authenticated = True
                    st.session_state.student_id = name_input
                    st.session_state.student_name = name_input
                    st.session_state.messages = []
                    st.session_state.conversation_ids = []
                    st.rerun()
                else:
                    st.error("이름 또는 비밀번호가 올바르지 않습니다.")


def student_mode():
    """학생용 챗봇 인터페이스"""
    st.title("🧪 화학 AI 튜터")
    st.markdown("---")

    # 로그인 정보 표시
    st.info(f"👤 **{st.session_state.get('student_name', '')}** 님, 환영합니다!")

    st.markdown("---")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_ids" not in st.session_state:
        st.session_state.conversation_ids = []

    if not st.session_state.messages:
        welcome_msg = "안녕하세요! 저는 여러분의 화학 학습을 도와주는 AI 튜터입니다. 화학에 관한 궁금한 점이 있으면 무엇이든 물어보세요! 😊"
        st.session_state.messages.append(
            {"role": "assistant", "content": welcome_msg, "id": None}
        )
        st.session_state.conversation_ids.append(None)

    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                display_assistant_message(message["content"])
            else:
                st.markdown(message["content"])

    if "pending_question" in st.session_state and st.session_state.pending_question:
        prompt = st.session_state.pending_question
        st.session_state.pending_question = None
    else:
        prompt = st.chat_input("화학 관련 질문을 입력하세요...")

    if prompt:
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "id": None}
        )
        st.session_state.conversation_ids.append(None)

        with st.chat_message("user"):
            st.markdown(prompt)

        clean_response = ""
        tag_string = "N/A"

        with st.chat_message("assistant"):
            with st.spinner("답변을 생성하는 중..."):
                all_messages = st.session_state.messages[:-1]
                chat_history_formatted = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in all_messages
                    if msg.get("id") is not None or msg["role"] == "user"
                ]

                raw_response = chat_with_chemistry_tutor(prompt, chat_history_formatted)
                clean_response, tag_string = parse_tag_from_response(raw_response)
                display_assistant_message(clean_response)

        try:
            conversation_id = save_conversation_to_db(
                student_id=st.session_state.student_id,
                device_id=st.session_state.get("browser_device_id", "Unknown"),
                question=prompt,
                answer=clean_response,
                content_element=tag_string,
            )

            st.session_state.messages.append(
                {"role": "assistant", "content": clean_response, "id": conversation_id}
            )
            st.session_state.conversation_ids.append(conversation_id)
            st.rerun()
        except Exception as e:
            st.error(f"데이터 저장 오류: {e}")
            st.session_state.messages.append(
                {"role": "assistant", "content": clean_response if clean_response else raw_response, "id": None}
            )
            st.session_state.conversation_ids.append(None)
            st.rerun()

    st.markdown("---")
    st.caption("💡 팁: 구체적으로 질문할수록 더 정확한 답변을 받을 수 있습니다!")


def teacher_dashboard():
    """교사용 대시보드 (학습 데이터 분석)"""
    st.title("📊 교사용 대시보드")
    
    st.subheader("📈 학습 데이터 조회")
    try:
        stats = get_statistics()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("총 대화 수", stats["total_conversations"])
        with col2:
            st.metric("참여 학생 수", stats["total_students"])
        with col3:
            st.metric("학생당 평균 질문", stats["avg_per_student"])
    except Exception as e:
        st.error(f"통계 로드 오류: {e}")
    
    st.markdown("---")
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("##### 📊 학생별 질문 횟수")
        try:
            student_counts = get_student_question_counts()
            if student_counts:
                df_students = pd.DataFrame(
                    [(s[0], s[1]) for s in student_counts],
                    columns=["학생ID", "질문수"]
                )
                fig = px.bar(df_students, x="학생ID", y="질문수", 
                             color="질문수", color_continuous_scale="Blues")
                fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("데이터가 없습니다.")
        except Exception as e:
            st.error(f"차트 로드 오류: {e}")
    
    with chart_col2:
        st.markdown("##### 🏷️ 성취기준별 질문 분포")
        try:
            element_dist = get_content_element_distribution()
            if element_dist:
                df_elements = pd.DataFrame(
                    [(e[0], e[1]) for e in element_dist],
                    columns=["성취기준", "질문수"]
                )
                fig = px.pie(df_elements, names="성취기준", values="질문수", 
                             hole=0.4)
                fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("데이터가 없습니다.")
        except Exception as e:
            st.error(f"차트 로드 오류: {e}")

    st.markdown("---")
    conversations = get_all_conversations()

    if not conversations:
        st.info("아직 저장된 대화 데이터가 없습니다.")
    else:
        st.caption("학생을 선택하여 대화 내용을 확인하세요.")
        student_list = list(set([conv.student_id for conv in conversations]))
        selected_student = st.selectbox(
            "학생 선택", ["전체"] + sorted(student_list)
        )

        filtered_conversations = conversations
        if selected_student != "전체":
            filtered_conversations = [
                c for c in filtered_conversations
                if c.student_id == selected_student
            ]

        st.markdown(f"**검색 결과:** 총 {len(filtered_conversations)}건의 대화")

        if filtered_conversations:
            with st.expander("📖 대화 내용 상세 보기", expanded=True):
                for conv in filtered_conversations:
                    time_str = conv.timestamp.strftime("%Y-%m-%d %H:%M")
                    st.markdown(f"**[{time_str}] {conv.student_id}**")
                    st.info(f"🗣️ 질문: {conv.question}")
                    st.success(f"🤖 답변: {conv.answer}")
                    if conv.content_element and conv.content_element != 'N/A':
                        st.caption(f"🏷️ 성취기준: {conv.content_element}")
                    st.markdown("---")
        else:
            st.warning("조건에 맞는 대화 내용이 없습니다.")

        st.markdown("---")
        st.subheader("💾 데이터 다운로드")
        df_data = []
        for conv in conversations:
            df_data.append({
                "학생ID": conv.student_id,
                "타임스탬프": conv.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "질문": conv.question,
                "답변": conv.answer,
                "성취기준": conv.content_element or "N/A",
            })
        df = pd.DataFrame(df_data)
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("📥 CSV 다운로드", csv, "data.csv", "text/csv")
        with d_col2:
            try:
                from io import BytesIO
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False)
                st.download_button("📥 Excel 다운로드", buffer.getvalue(), "data.xlsx")
            except:
                st.caption("Excel 다운로드 패키지 없음")
    
    st.markdown("---")
    st.subheader("⚠️ 기기 접속 차단 알림 (Realtime)")
    st.info("비정상적인 다른 기기 접속 시도 발생 시 실시간 알람이 표시됩니다.")
    
    # Supabase Realtime Javascript Component 삽입
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        
        realtime_js = f"""
        <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
        <div id="alert-container" style="font-family: sans-serif; color: #721c24; background-color: #f8d7da; padding: 10px; border-radius: 5px; display: none; margin-top: 10px; border: 1px solid #f5c6cb;">
           <strong>차단 알림!</strong> <span id="alert-msg"></span>
        </div>
        <script>
          const supabaseUrl = '{url}';
          const supabaseKey = '{key}';
          const supabaseClient = supabase.createClient(supabaseUrl, supabaseKey);
          
          supabaseClient
            .channel('blocked_logins_channel')
            .on('postgres_changes', {{ event: 'INSERT', schema: 'public', table: 'blocked_logins' }}, payload => {{
                console.log('Realtime event received!', payload);
                const msg = payload.new.student_id + " 학생 계정이 다른 기기(" + payload.new.attempted_device_id + ")에서 로그인을 시도하여 차단되었습니다.";
                const alertContainer = document.getElementById('alert-container');
                const alertMsg = document.getElementById('alert-msg');
                alertMsg.innerText = msg;
                alertContainer.style.display = 'block';
                // 브라우저 팝업
                window.parent.alert("⚠️ [기기 차단 경고]\\n\\n" + msg);
            }})
            .subscribe((status) => {{
               console.log('Realtime subscription status:', status);
            }});
        </script>
        """
        import streamlit.components.v1 as components
        components.html(realtime_js, height=80)
    except Exception as e:
        st.error("Realtime 알림 연결을 실패했습니다 (secrets 부족)")




# 메인 실행 로직 전 기기 ID(deviceId) 할당 검증
if "browser_device_id" not in st.session_state:
    st.title("🧪 화학 AI 튜터")
    st.markdown("---")
    
    with st.spinner("사용자 기기 정보를 동기화하는 중입니다... 잠시만 기다려주세요."):
        # localStorage에서 가져오거나 없으면 빈 문자열 반환하도록 JS 보강
        js_code = \"\"\"
        (function() {
            var dev = localStorage.getItem('device_id');
            return dev ? dev : 'NONE';
        })()
        \"\"\"
        dev_id = st_javascript(js_code)
        
        if dev_id == 0:
            # JS 로딩 중일 때 멈춤 보류
            st.stop()
        
        elif dev_id == 'NONE':
            # 저장된 기기 정보가 없을 경우 새로 발급
            new_uuid = str(uuid.uuid4())
            st_javascript(f"localStorage.setItem('device_id', '{new_uuid}');")
            st.session_state.browser_device_id = new_uuid
            st.rerun()
            
        else:
            # 기존 기기 정보 확인됨
            st.session_state.browser_device_id = dev_id
            st.rerun()

query_params = st.query_params
if "key" in query_params and query_params["key"] == "20237678":
    teacher_dashboard()
else:
    handle_login_sidebar()
    if st.session_state.get("pw_authenticated"):
        student_mode()
    else:
        st.title("🧪 화학 AI 튜터")
        st.markdown("---")
        st.markdown("### 👈 왼쪽 사이드바에서 로그인하세요")
        st.info("선생님이 나누어 준 이름(ID)과 6자리 비밀번호를 입력하면 학습을 시작할 수 있습니다.")
        st.markdown("---")
        st.caption("비밀번호를 모르는 경우 선생님께 문의하세요.")
