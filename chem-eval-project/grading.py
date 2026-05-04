import json
from data_utils import get_gemini_response # 기존 Gemini 연동 함수 활용

def grade_submission(scenario, student_answers):
    """
    Gemini API를 사용하여 학생의 6개 문항을 채점합니다.
    """
    prompt = f"""
    당신은 고등학교 화학 교사이며 수행평가 채점 위원입니다.
    다음 시나리오와 학생의 답안을 비교하여 6개 항목(파악 1~3, 교정 1~3)을 채점하세요.

    [시나리오 정보]
    - 주제: {scenario['theme']}
    - 각 항목 정답 가이드:
      1. 농도 오류: {scenario['error_1_info']}
      2. 압력 오류: {scenario['error_2_info']}
      3. 온도 오류: {scenario['error_3_info']}

    [학생 답안]
    - 오류파악1: {student_answers['det1']} / 교정1: {student_answers['cor1']}
    - 오류파악2: {student_answers['det2']} / 교정2: {student_answers['cor2']}
    - 오류파악3: {student_answers['det3']} / 교정3: {student_answers['cor3']}

    [채점 기준]
    1. 화학식(NH3, nh3, 암모니아 등)은 첨자나 대소문자 구분 없이 의미가 통하면 정답으로 인정하세요.
    2. '파악'은 AI 답변의 논리적 모순을 정확히 짚었는지, '교정'은 과학적 원리에 맞게 설명했는지 평가하세요.
    3. 각 항목당 true/false로만 판정하세요.

    [출력 형식 (JSON 전용)]
    {{
        "is_det_1_ok": bool, "is_cor_1_ok": bool,
        "is_det_2_ok": bool, "is_cor_2_ok": bool,
        "is_det_3_ok": bool, "is_cor_3_ok": bool,
        "ai_feedback": "학생에게 줄 따뜻한 격려와 피드백"
    }}
    """
    
    response = get_gemini_response(prompt)
    result = json.loads(response)
    
    # 루브릭 점수 계산 (6개 중 충족 개수)
    satisfied_count = sum([result[k] for k in result if k.startswith('is_')])
    score_map = {6: 20.0, 5: 17.5, 4: 15.0, 3: 12.5, 2: 10.0, 1: 7.5, 0: 5.0}
    final_score = score_map.get(satisfied_count, 5.0)
    
    return result, satisfied_count, final_score