import json
import requests
from user_db import STUDENT_LIST  # 개편된 학생 리스트 임포트
from database import get_supabase_config

def seed_database():
    """
    상당고 화학 수행평가 데이터를 Supabase에 일괄 업로드합니다.
    """
    base_url, headers = get_supabase_config()
    
    print("🚀 [상당고 수행평가] 데이터베이스 초기화를 시작합니다.")

    # 1. 학생 데이터 업로드
    print("\n👤 1/2. 학생 데이터 업로드 중...")
    # 기존 학생 데이터를 초기화하고 싶다면 아래 주석을 해제하세요.
    # requests.delete(f"{base_url}/students", headers=headers)
    
    resp_st = requests.post(
        f"{base_url}/students", 
        headers=headers, 
        json=STUDENT_LIST,
        verify=False
    )
    
    if resp_st.status_code in (200, 201, 204):
        print(f"✅ 학생 {len(STUDENT_LIST)}명 업로드 성공!")
    else:
        print(f"❌ 학생 업로드 실패: {resp_st.text}")

    # 2. 시나리오 데이터 업로드 (scenarios.json 파일에서 읽기)
    print("\n📝 2/2. 시나리오 데이터 업로드 중...")
    try:
        with open("scenarios.json", "r", encoding="utf-8") as f:
            scenarios_data = json.load(f)
            
        # 기존 시나리오 데이터를 초기화하고 싶다면 아래 주석을 해제하세요.
        # requests.delete(f"{base_url}/scenarios", headers=headers)
        
        resp_sc = requests.post(
            f"{base_url}/scenarios", 
            headers=headers, 
            json=scenarios_data,
            verify=False
        )
        
        if resp_sc.status_code in (200, 201, 204):
            print(f"✅ 시나리오 {len(scenarios_data)}개 업로드 성공!")
        else:
            print(f"❌ 시나리오 업로드 실패: {resp_sc.text}")
            
    except FileNotFoundError:
        print("⚠️ scenarios.json 파일이 존재하지 않습니다. 시나리오 업로드를 건너뜁니다.")
        print("💡 팁: Gems를 통해 만든 시나리오를 scenarios.json 파일로 저장해 주세요.")
    except json.JSONDecodeError:
        print("❌ scenarios.json 파일의 형식이 올바르지 않습니다.")
    except Exception as e:
        print(f"❌ 시나리오 업로드 중 예외 발생: {e}")

    print("\n🏁 모든 데이터 설정 작업이 종료되었습니다.")

if __name__ == "__main__":
    seed_database()