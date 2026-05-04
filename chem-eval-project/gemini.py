import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

def _get_client():
    """Gemini 클라이언트 초기화"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)

# --- 수행평가 자동 채점 프롬프트 ---
PERFORMANCE_GRADING_PROMPT = """당신은 고등학교 화학 교사이자 AI 융합 교육 전문가로서, 학생의 수행평가 답안을 채점하는 위원입니다.

## 📋 평가 과제: 화학 평형 AI 리포트 오류 정정
학생은 AI가 작성한 리포트(농도, 압력, 온도 관련 오류 포함)를 읽고, 각 답변에서 틀린 이유(오류 파악)와 바른 내용(교정)을 서술했습니다.

## ⚖️ 채점 기준 (루브릭)
1. **오류 파악(Detection)**: AI 답변의 논리적/학문적 결함이나 오개념의 원인을 정확히 지적했는가?
2. **정합적 교정(Correction)**: 르샤틀리에 원리, 평형 상수(K), 반응 지수(Q) 등을 활용하여 학문적으로 완벽하게 교정했는가?

## ⚠️ 채점 유의사항 (중요)
- **화학식 표기 관용**: NH3, nh3, 암모니아, [NH3] 등 대소문자나 첨자, 한글 명칭 혼용은 의미가 통하면 모두 정답으로 인정하세요.
- **논리적 일관성**: 단순 암기가 아니라 '변화 → 상쇄 방향 → 평형 이동'의 논리 구조가 맞으면 정답 처리하세요.
- **난이도 고려**: 고등학생 수준에서 이해 가능한 범위라면 정답으로 인정하되, 명백한 학문적 오류가 있다면 false 처리하세요.

## 📤 출력 형식 (반드시 JSON 형식만 출력)
{
    "is_det_1_ok": bool, "is_cor_1_ok": bool,
    "is_det_2_ok": bool, "is_cor_2_ok": bool,
    "is_det_3_ok": bool, "is_cor_3_ok": bool,
    "ai_feedback": "채점자(교사)를 위한 평가 보고서입니다. 1~6번 채점 항목이 각각 왜 정답(True) 혹은 오답(False)으로 평가되었는지 그 객관적 근거를 설명해주세요."
}"""

# --- 구조화된 출력 스키마 정의 (Pydantic을 사용하여 텍스트 잘림 방지 및 파싱 안정성 극대화) ---
class GradingResult(BaseModel):
    is_det_1_ok: bool
    is_cor_1_ok: bool
    is_det_2_ok: bool
    is_cor_2_ok: bool
    is_det_3_ok: bool
    is_cor_3_ok: bool
    ai_feedback: str


def grade_performance_task(scenario: dict, student_answers: dict) -> dict:
    """
    학생의 답안을 Gemini API로 전송하여 루브릭 기반으로 채점합니다.
    """
    client = _get_client()
    
    # 채점을 위한 컨텍스트 구성
    user_submission_context = f"""
[시나리오 정보]
- 테마: {scenario.get('theme')}
- 리포트 본문: {scenario.get('content')}
- 정답 가이드 (농도): {scenario.get('error_1_info')}
- 정답 가이드 (압력): {scenario.get('error_2_info')}
- 정답 가이드 (온도): {scenario.get('error_3_info')}

[학생 제출 답안]
1. 농도 영역 - 파악: {student_answers.get('det1')} / 교정: {student_answers.get('cor1')}
2. 압력 영역 - 파악: {student_answers.get('det2')} / 교정: {student_answers.get('cor2')}
3. 온도 영역 - 파악: {student_answers.get('det3')} / 교정: {student_answers.get('cor3')}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", # 최신 모델 적용 (기존 2.5 Flash 언급 반영 가능)
            contents=[types.Content(role="user", parts=[types.Part(text=user_submission_context)])],
            config=types.GenerateContentConfig(
                system_instruction=PERFORMANCE_GRADING_PROMPT,
                temperature=0.2, # 채점의 일관성을 위해 낮은 온도로 설정
                response_mime_type="application/json", # JSON 출력 강제
                response_schema=GradingResult, # Pydantic 모델을 스키마로 사용
                # max_output_tokens 제한 제거 (텍스트 잘림 현상 방지)
            ),
        )
        
        # SDK에서 제공하는 안전한 Pydantic 파싱 결과를 딕셔너리로 반환
        if response.parsed:
            return response.parsed.model_dump()
        else:
            return json.loads(response.text)
        
    except Exception as e:
        # 오류 발생 시 기본값 반환 (전부 False 처리 방지)
        print(f"채점 오류 발생: {e}")
        return {
            "is_det_1_ok": False, "is_cor_1_ok": False,
            "is_det_2_ok": False, "is_cor_2_ok": False,
            "is_det_3_ok": False, "is_cor_3_ok": False,
            "ai_feedback": "시스템 오류로 자동 채점이 중단되었습니다. 선생님께 문의하세요."
        }