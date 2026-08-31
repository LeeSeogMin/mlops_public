# 부록 A: 도구 설치 가이드
### Docker Compose 전체 환경

```yaml
# Docker Compose 최신 형식 (version 키 불필요)
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092

  postgres:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: public_data
      POSTGRES_USER: engineer
      POSTGRES_PASSWORD: password

  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.9.0
    ports:
      - "5000:5000"
    command: mlflow server --host 0.0.0.0

  prometheus:
    image: prom/prometheus:v2.47.0
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.1.0
    ports:
      - "3000:3000"
```

### Python 의존성

```
# 데이터 엔지니어링
apache-airflow==2.7.3
pyspark==3.5.0
kafka-python==2.0.2
delta-spark==3.0.0          # 데이터 레이크하우스
pyiceberg==0.5.0            # Apache Iceberg

# MLOps
mlflow==2.9.0
feast==0.35.0
scikit-learn==1.3.2
shap==0.43.0
skl2onnx==1.16.0            # 모델 경량화

# 서빙 & 테스트
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
locust==2.19.1
pytest==7.4.3
```

---