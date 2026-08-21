"""
데이터 파이프라인 핵심 컴포넌트

3.2 핵심 컴포넌트
- Kafka: 이벤트 스트리밍
- Spark: 실시간/배치 처리
- Airflow: 워크플로 오케스트레이션
- PostgreSQL/Iceberg: 저장소
- Prometheus/Grafana: 모니터링
"""

from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum


class ComponentCategory(Enum):
    """컴포넌트 카테고리"""
    MESSAGING = "messaging"
    PROCESSING = "processing"
    ORCHESTRATION = "orchestration"
    STORAGE = "storage"
    MONITORING = "monitoring"


@dataclass
class PipelineComponent:
    """파이프라인 컴포넌트 정의"""
    name: str
    category: ComponentCategory
    role: str
    public_sector_considerations: List[str]
    key_configs: Dict[str, str]
    alternatives: List[str]


# 핵심 컴포넌트 정의
PIPELINE_COMPONENTS: Dict[str, PipelineComponent] = {
    "kafka": PipelineComponent(
        name="Apache Kafka",
        category=ComponentCategory.MESSAGING,
        role="이벤트 스트리밍 플랫폼 - 실시간 데이터 수집 및 전달",
        public_sector_considerations=[
            "전송 암호화 (TLS 1.3) 필수 설정",
            "감사 로그 활성화 (log4j 설정)",
            "토픽별 접근 제어 (ACL)",
            "데이터 보관 기간 설정 (retention.ms)",
            "클러스터 이중화 (최소 3 브로커)",
        ],
        key_configs={
            "security.protocol": "SSL",
            "ssl.endpoint.identification.algorithm": "https",
            "log.retention.hours": "168",  # 7일
            "min.insync.replicas": "2",
            "acks": "all",
            "enable.idempotence": "true",
            "max.in.flight.requests.per.connection": "5",
        },
        alternatives=["Apache Pulsar", "AWS Kinesis", "Azure Event Hubs"],
    ),

    "spark_streaming": PipelineComponent(
        name="Apache Spark Streaming",
        category=ComponentCategory.PROCESSING,
        role="실시간 스트림 처리 - 마이크로배치 기반 스트리밍",
        public_sector_considerations=[
            "Watermark 설정으로 지연 데이터 처리",
            "체크포인트 설정으로 장애 복구",
            "메모리 관리 최적화",
            "개인정보 마스킹 UDF 적용",
        ],
        key_configs={
            "spark.sql.streaming.checkpointLocation": "/checkpoint",
            "spark.sql.streaming.minBatchesToRetain": "100",
            "spark.streaming.backpressure.enabled": "true",
            "spark.streaming.kafka.maxRatePerPartition": "1000",
        },
        alternatives=["Apache Flink", "Apache Storm", "Kafka Streams"],
    ),

    "spark_batch": PipelineComponent(
        name="Apache Spark Batch",
        category=ComponentCategory.PROCESSING,
        role="대용량 배치 처리 - 야간 집계 및 분석",
        public_sector_considerations=[
            "야간 시간대 실행으로 비용 절감",
            "파티셔닝 전략으로 성능 최적화",
            "결과 검증 로직 포함",
            "실패 시 재시도 및 알림",
        ],
        key_configs={
            "spark.sql.shuffle.partitions": "200",
            "spark.sql.adaptive.enabled": "true",
            "spark.dynamicAllocation.enabled": "true",
            "spark.sql.parquet.compression.codec": "snappy",
        },
        alternatives=["Apache Hadoop MapReduce", "Dask", "Presto"],
    ),

    "airflow": PipelineComponent(
        name="Apache Airflow",
        category=ComponentCategory.ORCHESTRATION,
        role="워크플로 오케스트레이션 - DAG 기반 작업 스케줄링",
        public_sector_considerations=[
            "SLA 알림 설정 (기한 초과 시)",
            "실패 재시도 정책 설정",
            "민감 정보 Connections/Variables 암호화",
            "RBAC으로 DAG별 접근 제어",
            "실행 로그 장기 보관",
        ],
        key_configs={
            "default_task_retries": "3",
            "sla_miss_callback": "alert_function",
            "fernet_key": "[암호화 키]",
            "rbac": "True",
            "log_retention_days": "365",
        },
        alternatives=["Prefect", "Dagster", "Luigi", "Argo Workflows"],
    ),

    "postgresql": PipelineComponent(
        name="PostgreSQL",
        category=ComponentCategory.STORAGE,
        role="서빙 레이어 DB - 실시간 조회용 RDBMS",
        public_sector_considerations=[
            "개인정보 컬럼 암호화 (pgcrypto)",
            "접근 로그 기록 (pgaudit)",
            "자동 백업 설정",
            "읽기 복제본 구성 (고가용성)",
            "연결 풀링 (PgBouncer)",
        ],
        key_configs={
            "ssl": "on",
            "log_statement": "all",
            "shared_preload_libraries": "pgaudit",
            "wal_level": "replica",
            "max_connections": "200",
        },
        alternatives=["MySQL", "Oracle", "SQL Server", "CockroachDB"],
    ),

    "delta_lake": PipelineComponent(
        name="Delta Lake",
        category=ComponentCategory.STORAGE,
        role="레이크하우스 저장소 - ACID 트랜잭션, 시간 여행",
        public_sector_considerations=[
            "시간 여행으로 감사 추적 대응",
            "스키마 진화로 정책 변경 대응",
            "Z-Order 인덱싱으로 쿼리 최적화",
            "Vacuum으로 데이터 정리 (보관 기간 준수)",
        ],
        key_configs={
            "delta.logRetentionDuration": "interval 30 days",
            "delta.deletedFileRetentionDuration": "interval 7 days",
            "delta.enableChangeDataFeed": "true",
            "delta.autoOptimize.optimizeWrite": "true",
        },
        alternatives=["Apache Iceberg", "Apache Hudi"],
    ),

    "prometheus": PipelineComponent(
        name="Prometheus",
        category=ComponentCategory.MONITORING,
        role="메트릭 수집 및 저장 - 시계열 모니터링 데이터베이스",
        public_sector_considerations=[
            "장기 보관을 위한 원격 저장소 연동",
            "알림 규칙 설정 (AlertManager)",
            "서비스 디스커버리 설정",
            "보안 엔드포인트 설정",
        ],
        key_configs={
            "scrape_interval": "15s",
            "evaluation_interval": "15s",
            "retention.time": "15d",
            "storage.tsdb.path": "/prometheus",
        },
        alternatives=["InfluxDB", "VictoriaMetrics", "Datadog"],
    ),

    "grafana": PipelineComponent(
        name="Grafana",
        category=ComponentCategory.MONITORING,
        role="시각화 및 대시보드 - 메트릭 시각화, 알림 관리",
        public_sector_considerations=[
            "LDAP/OAuth 연동으로 인증 통합",
            "대시보드 버전 관리",
            "알림 채널 설정 (이메일, Slack 등)",
            "익명 접근 비활성화",
        ],
        key_configs={
            "auth.anonymous.enabled": "false",
            "security.admin_password": "[강력한 비밀번호]",
            "alerting.enabled": "true",
            "server.protocol": "https",
        },
        alternatives=["Kibana", "Superset", "Metabase"],
    ),
}


class ComponentDiagram:
    """컴포넌트 연결 다이어그램"""

    @staticmethod
    def data_flow_diagram() -> str:
        """데이터 흐름 다이어그램"""
        return """
┌─────────────────────────────────────────────────────────────────────────────┐
│                        데이터 파이프라인 컴포넌트 연결도                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [데이터 수집]                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                                  │
│  │ 민원 API │  │ 재난 피드│  │ 센서     │                                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                                  │
│       │             │             │                                         │
│       └─────────────┼─────────────┘                                         │
│                     ▼                                                       │
│  [메시징]    ┌─────────────────────────────────────┐                       │
│              │            Apache Kafka             │                       │
│              │  • 이벤트 스트리밍                  │                       │
│              │  • 토픽: complaints, disasters, ...│                       │
│              │  • 파티션으로 병렬 처리             │                       │
│              └─────────────┬───────────────────────┘                       │
│                            │                                                │
│         ┌──────────────────┼──────────────────┐                            │
│         ▼                  ▼                  ▼                            │
│  [처리] ┌────────────┐ ┌────────────┐ ┌────────────────┐                   │
│         │  Spark     │ │  Spark     │ │   Airflow      │                   │
│         │ Streaming  │ │  Batch     │ │ (오케스트레이션)│                   │
│         │ - 실시간   │ │ - 야간배치 │ │ - DAG 스케줄링 │                   │
│         │ - 분류     │ │ - 집계     │ │ - 의존성 관리  │                   │
│         └─────┬──────┘ └─────┬──────┘ └────────────────┘                   │
│               │              │                                              │
│               └──────┬───────┘                                              │
│                      ▼                                                      │
│  [저장]    ┌─────────────────────────────────────┐                         │
│            │    Delta Lake / Apache Iceberg      │                         │
│            │  • ACID 트랜잭션                    │                         │
│            │  • 시간 여행 (감사 추적)            │                         │
│            │  • 스키마 진화                      │                         │
│            └─────────────────┬───────────────────┘                         │
│                              │                                              │
│         ┌────────────────────┼────────────────────┐                        │
│         ▼                    ▼                    ▼                        │
│  [서빙] ┌────────────┐ ┌────────────┐ ┌────────────┐                       │
│         │ PostgreSQL │ │ ML 서빙   │ │ API 서버  │                       │
│         │ (조회용)   │ │ (예측)    │ │ (REST)    │                       │
│         └────────────┘ └────────────┘ └────────────┘                       │
│                                                                             │
│  [모니터링] ┌─────────────────────────────────────┐                        │
│             │     Prometheus + Grafana            │                        │
│             │  • 메트릭 수집 (scrape)             │                        │
│             │  • 대시보드 시각화                  │                        │
│             │  • 알림 (AlertManager)              │                        │
│             └─────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
"""

    @staticmethod
    def component_interaction() -> str:
        """컴포넌트 상호작용 다이어그램"""
        return """
┌─────────────────────────────────────────────────────────────────────────────┐
│                        컴포넌트 상호작용 매트릭스                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                      Kafka  Spark  Airflow  Delta  PgSQL  Prom   Grafana   │
│                      ─────  ─────  ───────  ─────  ─────  ────   ───────   │
│  Kafka               ─────  READ   TRIGGER  ────   ────   PUSH   ────      │
│  Spark Streaming     SUB    ─────  ───────  WRITE  WRITE  PUSH   ────      │
│  Spark Batch         SUB    ─────  TRIGGER  R/W    WRITE  PUSH   ────      │
│  Airflow             ─────  SCHED  ───────  ─────  META   PUSH   ────      │
│  Delta Lake          ─────  ─────  ───────  ─────  ─────  ────   ────      │
│  PostgreSQL          ─────  ─────  ───────  ─────  ─────  PUSH   ────      │
│  Prometheus          ─────  ─────  ───────  ─────  ─────  ─────  PULL      │
│  Grafana             ─────  ─────  ───────  ─────  QUERY  QUERY  ─────     │
│                                                                             │
│  범례: SUB=Subscribe, READ=Read, WRITE=Write, PUSH=Push metrics,           │
│        PULL=Pull data, SCHED=Schedule, TRIGGER=Trigger, QUERY=Query        │
└─────────────────────────────────────────────────────────────────────────────┘
"""


def print_component_summary():
    """컴포넌트 요약 출력"""
    print("=" * 80)
    print("데이터 파이프라인 핵심 컴포넌트")
    print("=" * 80)

    categories = {}
    for comp in PIPELINE_COMPONENTS.values():
        cat = comp.category.value
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(comp)

    category_names = {
        "messaging": "메시징",
        "processing": "처리",
        "orchestration": "오케스트레이션",
        "storage": "저장소",
        "monitoring": "모니터링",
    }

    for cat, components in categories.items():
        print(f"\n[{category_names.get(cat, cat).upper()}]")
        print("-" * 60)

        for comp in components:
            print(f"\n  {comp.name}")
            print(f"    역할: {comp.role}")
            print(f"    공공 영역 고려사항:")
            for consideration in comp.public_sector_considerations[:2]:
                print(f"      • {consideration}")


def print_component_configs():
    """컴포넌트 주요 설정 출력"""
    print("\n" + "=" * 80)
    print("컴포넌트별 주요 설정 (공공 영역)")
    print("=" * 80)

    for name, comp in PIPELINE_COMPONENTS.items():
        print(f"\n[{comp.name}]")
        print("-" * 40)
        for key, value in list(comp.key_configs.items())[:4]:
            print(f"  {key}: {value}")


def demo():
    """컴포넌트 데모"""
    print_component_summary()

    diagram = ComponentDiagram()
    print("\n" + "=" * 80)
    print("데이터 흐름 다이어그램")
    print("=" * 80)
    print(diagram.data_flow_diagram())

    print_component_configs()


if __name__ == "__main__":
    demo()
