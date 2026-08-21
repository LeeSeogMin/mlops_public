#!/usr/bin/env python3
"""
Chapter 3: 데이터 파이프라인 아키텍처 설계
==========================================

이 스크립트는 Chapter 3의 모든 실습을 순차적으로 실행합니다.

학습 목표:
- 실시간·배치 하이브리드 아키텍처(Lambda/Kappa)를 비교하고 적절한 상황을 판단할 수 있다.
- 공공 영역 요구사항(감사, 보안, 규제)을 반영한 아키텍처를 설계할 수 있다.
- 주요 컴포넌트(Kafka, Spark, Airflow)의 역할과 연결 관계를 도식화할 수 있다.

실습 난이도: ★★★☆☆
"""

import sys
import os
from datetime import datetime

# 소스 디렉토리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def print_header(title: str):
    """섹션 헤더 출력"""
    width = 70
    print("\n\n")
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_subheader(title: str):
    """서브섹션 헤더 출력"""
    print(f"\n--- {title} ---")


def section_1_architecture_patterns():
    """3.1 아키텍처 패턴"""
    print_header("3.1 아키텍처 패턴")

    from architecture import (
        ARCHITECTURE_PATTERNS, ArchitectureType,
        ArchitectureDiagram, ArchitectureComparator
    )

    # 패턴 요약
    print("\n[아키텍처 패턴 요약]")
    print("-" * 60)

    for arch_type, pattern in ARCHITECTURE_PATTERNS.items():
        print(f"\n  [{pattern.name}]")
        print(f"    {pattern.description}")
        print(f"    공공 적합도: {pattern.public_sector_fit}")

    # 다이어그램
    print_subheader("공공 영역 권장 아키텍처 다이어그램")
    diagrams = ArchitectureDiagram()
    print(diagrams.hybrid_architecture())

    # 비교표
    print_subheader("아키텍처 패턴 비교")
    comparator = ArchitectureComparator()
    print(comparator.compare_all())


def section_2_core_components():
    """3.2 핵심 컴포넌트"""
    print_header("3.2 핵심 컴포넌트")

    from components import PIPELINE_COMPONENTS, ComponentDiagram

    # 컴포넌트 요약
    print("\n[파이프라인 컴포넌트]")

    categories = {
        "messaging": "메시징",
        "processing": "처리",
        "orchestration": "오케스트레이션",
        "storage": "저장소",
        "monitoring": "모니터링",
    }

    for comp_name, comp in PIPELINE_COMPONENTS.items():
        cat_name = categories.get(comp.category.value, comp.category.value)
        if comp_name in ["kafka", "spark_streaming", "airflow", "delta_lake", "prometheus"]:
            print(f"\n  [{cat_name.upper()}] {comp.name}")
            print(f"    역할: {comp.role}")
            print(f"    공공 고려사항:")
            for consideration in comp.public_sector_considerations[:2]:
                print(f"      • {consideration}")

    # 데이터 흐름 다이어그램
    print_subheader("데이터 흐름 다이어그램")
    diagram = ComponentDiagram()
    print(diagram.data_flow_diagram())


def section_3_public_requirements():
    """3.3 공공 영역 아키텍처 요구사항"""
    print_header("3.3 공공 영역 아키텍처 요구사항")

    from security import (
        SECURITY_REQUIREMENTS, AUDIT_REQUIREMENTS, COMPLIANCE_REQUIREMENTS,
        SecurityChecklistGenerator
    )

    # 보안 요구사항
    print_subheader("3.3.1 보안 요구사항")
    for name, req in list(SECURITY_REQUIREMENTS.items())[:3]:
        print(f"\n  [{req.category}]")
        for r in req.requirements[:2]:
            print(f"    • {r}")

    # 감사 요구사항
    print_subheader("3.3.2 감사 요구사항")
    for name, req in AUDIT_REQUIREMENTS.items():
        print(f"\n  [{req.category}]")
        for r in req.requirements[:2]:
            print(f"    • {r}")

    # 규제 준수
    print_subheader("3.3.3 규제 준수")
    for name, req in COMPLIANCE_REQUIREMENTS.items():
        print(f"\n  [{req.category}]")
        for r in req.requirements[:2]:
            print(f"    • {r}")

    # 체크리스트
    print_subheader("보안 체크리스트")
    generator = SecurityChecklistGenerator()
    print(generator.generate_security_checklist())


def section_4_cloud_options():
    """3.4 공공 클라우드 환경 선택"""
    print_header("3.4 공공 클라우드 환경 선택")

    from security import CLOUD_OPTIONS, SecurityChecklistGenerator

    print("\n[클라우드 옵션 비교]")
    print("-" * 60)

    for cloud_type, option in CLOUD_OPTIONS.items():
        print(f"\n  [{option.name}]")
        print(f"    {option.description}")
        print(f"    적합: {', '.join(option.suitable_for[:2])}")

    # 선택 가이드
    print_subheader("클라우드 선택 가이드")
    generator = SecurityChecklistGenerator()
    print(generator.generate_cloud_selection_guide())


def section_5_docker_compose():
    """실습 3.1: Docker Compose 기반 파이프라인"""
    print_header("실습 3.1: Docker Compose 기반 파이프라인")

    print("""
[Docker Compose 구성]

제공된 docker-compose.yml 파일에는 다음 서비스가 포함되어 있습니다:

┌──────────────────────────────────────────────────────────────────┐
│ Service      │ Port  │ 역할                                     │
├──────────────────────────────────────────────────────────────────┤
│ zookeeper    │ 2181  │ Kafka 클러스터 관리                      │
│ kafka        │ 9092  │ 이벤트 스트리밍                          │
│ postgres     │ 5432  │ 서빙 레이어 DB                           │
│ prometheus   │ 9090  │ 메트릭 수집                              │
│ grafana      │ 3000  │ 시각화 대시보드                          │
│ kafka-ui     │ 8080  │ Kafka 모니터링 (개발용)                  │
└──────────────────────────────────────────────────────────────────┘

[실행 방법]

  # 1. 디렉토리 이동
  cd practice/chapter3

  # 2. 컨테이너 실행
  docker-compose up -d

  # 3. 상태 확인
  docker-compose ps

  # 4. Kafka 토픽 생성
  docker exec kafka kafka-topics --create \\
    --topic complaints --bootstrap-server localhost:9092 --partitions 3

  # 5. 서비스 접속
  - Kafka UI: http://localhost:8080
  - Grafana: http://localhost:3000 (admin/admin)
  - Prometheus: http://localhost:9090
""")

    print_subheader("Kafka 시뮬레이션 데모")

    from kafka_demo import PublicDataKafkaDemo
    kafka_demo = PublicDataKafkaDemo()
    kafka_demo.setup_topics()
    kafka_demo.demo_producer(count=3)
    kafka_demo.demo_consumer()
    kafka_demo.demo_message_flow()


def section_6_exercises():
    """연습 문제"""
    print_header("연습 문제")

    from exercises import run_all_exercises
    run_all_exercises()


def main():
    """메인 실행 함수"""
    start_time = datetime.now()

    print("\n" + "#" * 70)
    print("#" * 70)
    print("##" + " " * 66 + "##")
    print("##   Chapter 3: 데이터 파이프라인 아키텍처 설계" + " " * 18 + "##")
    print("##" + " " * 66 + "##")
    print("##   실습 난이도: ★★★☆☆" + " " * 40 + "##")
    print("##" + " " * 66 + "##")
    print("#" * 70)
    print("#" * 70)

    print(f"\n실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    # 각 섹션 실행
    section_1_architecture_patterns()
    section_2_core_components()
    section_3_public_requirements()
    section_4_cloud_options()
    section_5_docker_compose()
    section_6_exercises()

    # 완료
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("Chapter 3 실습 완료!")
    print("=" * 70)
    print(f"  시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  소요 시간: {duration:.2f}초")
    print("\n[다음 단계]")
    print("  Chapter 4: 피처 엔지니어링 파이프라인 구축으로 이동하세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
