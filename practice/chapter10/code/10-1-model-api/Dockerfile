# 10장 실습: 모델 API 이미지 — 코드 + 의존성 + champion 실물을 하나의 불변 단위로 포장
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
ENV CH10_MODEL_URI=/app/model \
    CH10_EXPORT_INFO=/app/export_info.json \
    CH10_CHALLENGER_URI=off

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
