# 13주차 통합 MVP: 파이프라인 이미지 — ingester(발행)와 processor(소비·정제·집계·예측 호출)가
# 같은 이미지를 공유한다(compose의 command로 역할이 갈린다)
FROM python:3.13-slim

WORKDIR /app

COPY requirements-pipeline.txt ./
RUN pip install --no-cache-dir -r requirements-pipeline.txt

COPY ingester.py processor.py ./

# 기본 명령은 processor(장기 실행 서비스) — ingester는 compose run으로 단발 실행
CMD ["python", "-u", "processor.py"]
