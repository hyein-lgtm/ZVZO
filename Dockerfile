# Playwright 공식 이미지 = 크롬 브라우저 + 필요한 시스템 라이브러리가 이미 깔려 있음
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway가 주는 포트($PORT)로 서버 실행
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
