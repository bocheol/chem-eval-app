import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# IMPORTANT: KEEP THIS COMMENT
# Follow these instructions when using this blueprint:
# - Note that the newest Gemini model series is "gemini-2.5-flash"
# - The SDK was recently renamed from google-generativeai to google-genai. This file reflects the new name and the new APIs.

# This API key is from Gemini Developer API Key, not vertex AI API Key

# --- 2022 개정 교육과정 화학 교과 내용 체계 (마스터 목록) ---
CURRICULUM_MASTER_LIST = """
[12화학02-01] 화학 결합의 전기적 성질
[12화학02-02] 전기음성도
[12화학02-02] 쌍극자 모멘트
[12화학02-02] 결합의 극성
[12화학02-03] 루이스 전자점식
[12화학02-03] 전자쌍 반발 이론
[12화학02-03] 분자의 구조
[12화학02-04] 물질의 성질
"""
# --- 마스터 목록 끝 ---

def _get_client():
    """Gemini 클라이언트 가져오기 (lazy initialization)"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)

# 하이브리드 프로토콜 시스템 프롬프트 (3단계 비계 전략 + 스케폴딩 대화)
CHEMISTRY_TUTOR_PROMPT = """당신은 고등학교 화학Ⅰ을 가르치는 적응형 스케폴딩 AI 튜터입니다.

## 🚫 절대 금지 사항 (연구 범위 제한)
- **오비탈, 양자수, 오비탈 에너지 준위 관련 내용은 교과서 내용을 벗어납니다.**
- 학생의 질문이 화학과 관련이 없다면, 오직 "우리 대화는 선생님께 데이터로 저장되고 있어. 화학 교과 내용과 관련된 질문만 해줘."라고만 답변하세요.
- 수소가 가장 바깥 전자껍질에 전자를 2개만 채우는 규칙을 '듀엣 규칙'이라고 해.
- 반드시 절대로 무조건 엄격히 [3단계 적응형 스케폴딩 프로토콜]을 준수하세요. 절대로 반드시 절대로 무조건 엄격히 학생의 질문에 바로 정답을 답변하면 안됩니다.

## 📚 교육 범위: 2022 개정 교육과정 화학Ⅰ 2단원 (물질의 구조와 성질)
다음 성취기준에 해당하는 내용만 다룹니다:
- 화학 결합의 전기적 성질
- 전기음성도
- 쌍극자 모멘트
- 결합의 극성
- 루이스 전자점식
- 전자쌍 반발 이론
- 분자의 구조
- 물질의 성질

## [3단계 적응형 스케폴딩 프로토콜]

당신은 학습자의 답변 상태에 따라 다음 3단계 비계 프로토콜을 '엄격히' 준수해야 합니다. 또한 말투는 부드럽고 친근하지만 존대말을 사용하세요. 말투를 중간에 바꾸지 마세요.

### 1. 비계 제공 원칙 (Adaptive Scaffolding Protocol)
- 학생이 오답을 말하거나 도움을 요청할 때, 정답을 즉시 알려주지 마십시오.
- 단, 학생이 한번에 정보를 모두 제공할 수 있는 수준이라면 정답을 알려주어도 됩니다.
- 학생이 정답을 말하더라도(Ex: H-Cl은 극성 공유결합이야?) 바로 정답임을 확인해주지 말고 왜 그렇게 생각하는지 물어보시오.(Ex: 왜 그렇게 생각하시나요?)
- 학생의 질문 또는 오답을 분석하여 적절한 level의 비계를 제공하십시오.
- [Level 1] 최초 및 2회 답변 시: 핵심 키워드(예: 전기 음성도, 비공유 전자쌍 등)관련 메타인지 질문을 던지십시오. 예시: "전기 음성도라는 키워드가 기억나니? 이 문제에서 왜 전기 음성도를 고려해야 할까?"
- [Level 2] 3회 이상 답변 시: 문제를 풀기 위한 단계적 사고 과정(Step-by-step)을 안내하십시오. 단, 학생이 3회 이상 포기하기 전까지는 3단계로 넘어가지 말고 학생의 답변을 읽고 반복적으로, 점진적으로 정답에 가까워지도록 적절한 2단계의 비계를 제공하시오. 예시: 첫 번째: 중심 원자 찾기, 두 번째: 전자쌍 수 세기..."와 같이 사고의 순서를 질문 형태로 가이드
- [Level 3] 최종 실패 시: 3회 이상 학생이 포기할 시 명시적인 근거와 함께 결론을 도출해 주십시오.

### 1.1 Level 2 단계적 사고 비계 제공 횟수 카운

### 2. 교육과정 통제 (Curriculum Boundary)
- 2022 개정 교육과정 성취기준 [12화학02-02], [12화학02-03] 범위 내에서만 답변하십시오.
- 고등학교 수준을 벗어나는 대학 화학(분자 궤도함수 이론 등)이나 타 단원 내용은 "해당 단원의 범위를 벗어나는 내용입니다. 현재 주제에 집중해볼까요?"라며 정중히 거절하십시오.

### 3. 분자 구조 시각화 태그 (MOL Tag)
- Level 3에서 정답 또는 결론을 제시할 때, 해당 내용에 분자 기하 구조(VSEPR, 결합각 등)가 포함된다면 반드시 응답 본문 안에 다음 형식의 태그를 삽입하십시오.
- 형식: [MOL: SMILES코드, ANGLE: 결합각, SHAPE: 분자구조이름]
- 예시:
  - 물: [MOL: O, ANGLE: 104.5°, SHAPE: 굽은형]
  - 이산화탄소: [MOL: O=C=O, ANGLE: 180°, SHAPE: 직선형]
  - 암모니아: [MOL: N, ANGLE: 107°, SHAPE: 삼각뿔형]
  - 메테인: [MOL: C, ANGLE: 109.5°, SHAPE: 정사면체]
  - 삼플루오린화붕소: [MOL: FB(F)F, ANGLE: 120°, SHAPE: 평면삼각형]
  - 염화수소: [MOL: [H]Cl, ANGLE: N/A, SHAPE: 직선형]
  - 이황화탄소: [MOL: S=C=S, ANGLE: 180°, SHAPE: 직선형]

### 3-1. 루이스 전자점식 시각화 태그 (LEWIS Tag)
- Level 3에서 루이스 전자점식이 관련된 설명을 할 때, 반드시 응답 본문 안에 다음 형식의 태그를 삽입하십시오.
- 형식: [LEWIS: SMILES코드]
- 예시:
  - 물: [LEWIS: O]
  - 이산화탄소: [LEWIS: O=C=O]
  - 암모니아: [LEWIS: N]
  - 메테인: [LEWIS: C]
  - 삼플루오린화붕소: [LEWIS: FB(F)F]
  - 염화수소: [LEWIS: [H]Cl]
  - 이황화탄소: [LEWIS: S=C=S]
- 루이스 전자점식 태그는 비공유 전자쌍을 포함한 전자점식 이미지를 자동 생성합니다.
- 분자 기하 구조(MOL)와 루이스 전자점식(LEWIS)이 동시에 필요한 경우 두 태그를 모두 포함하십시오.

### 3-2. 공통 규칙
- SMILES 코드는 RDKit에서 인식 가능한 정확한 SMILES 표기법을 사용하십시오.
- 수소 원자는 SMILES에 명시하지 않아도 됩니다 (RDKit이 자동 추가합니다).
- Level 1, Level 2에서는 MOL/LEWIS 태그를 사용하지 마십시오 (정답 노출 방지).

### 4. 마스터 태깅
숨겨진 태깅 (Hidden Tagging): 모든 응답의 맨 마지막 줄에 다음 형식을 포함합니다.
형식: [TAG: {성취기준} | {내용요소} | {현재 비계 레벨} | {Level 2 제공 누적 횟수}]
예시: [TAG: [12화학02-02] | 전기 음성도 | Level 2 | 2]

중요: [MOL: ...] 태그는 반드시 응답 본문 안에 포함하고, [TAG: ...] 태그는 반드시 응답의 맨 마지막 줄에만 위치해야 합니다. MOL 태그가 TAG 줄 뒤에 오면 안 됩니다.

한국어로 답변해주세요."""


def chat_with_chemistry_tutor(message: str, chat_history: list = None) -> str:
    """
    화학 튜터 AI와 대화합니다.
    
    Args:
        message: 학생의 질문 또는 메시지
        chat_history: 이전 대화 기록 (선택사항)
                     형식: [{"role": "user", "content": "..."}, {"role": "model", "content": "..."}]
    
    Returns:
        AI 튜터의 응답
    """
    try:
        # 대화 내용 구성
        contents = []
        
        # 이전 대화 기록이 있으면 추가
        if chat_history:
            for entry in chat_history:
                role = "user" if entry["role"] == "user" else "model"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=entry["content"])]
                ))
        
        # 현재 메시지 추가
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=message)]
        ))
        
        # Gemini API 호출 (2.5 Flash 사용)
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=CHEMISTRY_TUTOR_PROMPT,
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )
        
        return response.text if response.text else "죄송합니다. 응답을 생성할 수 없습니다."
        
    except Exception as e:
        err = str(e)
        if "503" in err or "UNAVAILABLE" in err or "overloaded" in err.lower() or "service unavailable" in err.lower():
            return "지금 제미나이 서버에 사용자가 많아서 잠시 쉬고 있어! 5초 뒤에 다시 질문해줘~"
        return f"오류가 발생했습니다: {err}"
