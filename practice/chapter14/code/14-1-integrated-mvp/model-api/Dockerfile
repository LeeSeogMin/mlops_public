# 14장 통합 MVP: 모델 API 이미지 — 10장 Dockerfile 규약 그대로(코드+의존성+champion 고정)
# app.py는 10장 파일의 바이트 동일 복사본이다(run_chapter14.py가 sha256 일치 확인).
FROM python:3.13-slim

WORKDIR /app

# 의존성 층을 코드보다 먼저 — 코드만 바뀌면 이 층은 캐시로 재사용된다
COPY requirements-serve.txt ./
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY app.py ./
# 빌드 시점의 champion 실물(bootstrap이 model_export/에 내려받아 둔 것)을 고정
COPY model_export/model ./model
COPY model_export/export_info.json ./export_info.json

# 컨테이너는 레지스트리를 보지 않는다 — 이미지에 고정된 모델만 서빙(폐쇄망에서도 동작)
# 환경변수 이름이 CH10_*인 것은 서빙 앱이 10장 부품이기 때문이다(재조립 — 이름도 신원이다)
ENV CH10_MODEL_URI=/app/model \
    CH10_EXPORT_INFO=/app/export_info.json \
    CH10_CHALLENGER_URI=off

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
