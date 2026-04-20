# 1. 정규 버전 이미지 사용 (안정성 확보)
FROM python:3.11-slim-bookworm 
# slim이라도 아래의 apt-get 설정을 넣으면 훨씬 가볍고 확실하게 돌아갑니다.

# 2. 리눅스 시스템 필수 패키지 설치 (RDKit 및 그래픽 구동용)
RUN apt-get update && apt-get install -y \
    libxrender1 \
    libxext6 \
    libfontconfig1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 필요한 파일 복사
COPY . .

# 5. 파이썬 라이브러리 설치
RUN pip install --no-cache-dir -r requirements.txt

# 6. 구글 클라우드 런 포트 설정
ENV PORT 8080
EXPOSE 8080

# 7. 필수 누락 구문: 앱 실행 명령어
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
