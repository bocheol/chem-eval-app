# -*- coding: utf-8 -*-
from database import get_supabase_config, register_student_device, get_student_device, log_blocked_attempt
import traceback
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

def test_supabase():
    try:
        print("1. Supabase 접속 정보 로드 시도 중...")
        get_supabase_config()
        print("OK: 정보 로딩 성공")
        
        print("2. 기기 등록 테스트 (student_id: test_01, device_id: dev_999)")
        register_student_device("test_01", "dev_999")
        print("OK: 등록 완료")
        
        print("3. 기기 조회 테스트")
        dev = get_student_device("test_01")
        if dev == "dev_999":
            print("OK: 조회 성공 (결과 일치)")
        else:
            print(f"FAIL: 불일치: {dev}")
            
        print("4. 차단 기록 등록 테스트")
        log_blocked_attempt("test_01", "dev_888")
        print("OK: 기록 완료")
        
        print("모든 DB 기본 기능 정상 동작을 확인했습니다.")
    except Exception as e:
        print("FAIL: 테스트 중 오류 발생:")
        traceback.print_exc()

if __name__ == "__main__":
    test_supabase()
