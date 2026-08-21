#!/usr/bin/env python3
"""
Chapter 1: 데이터 엔지니어링과 MLOps의 개요
==========================================

이 스크립트는 Chapter 1의 모든 실습을 순차적으로 실행합니다.

학습 목표:
- DE와 MLOps의 정의, 역할, 차이점을 설명할 수 있다.
- 공공 영역에서 DE-MLOps 통합이 필요한 이유를 사례와 함께 논증할 수 있다.
- 실시간 데이터 파이프라인의 기본 구조를 도식화할 수 있다.

실습 난이도: ★☆☆☆☆
"""

import sys
import os
from datetime import datetime
import json

# 소스 디렉토리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def print_header(title: str):
    """섹션 헤더 출력"""
    width = 70
    print("\n")
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_subheader(title: str):
    """서브섹션 헤더 출력"""
    print(f"\n--- {title} ---")


def section_1_data_engineering():
    """1.1 데이터 엔지니어링의 정의와 역할"""
    print_header("1.1 데이터 엔지니어링의 정의와 역할")

    print("""
데이터 엔지니어링은 데이터의 수집, 저장, 변환, 제공을 위한
인프라와 파이프라인을 설계·구축·운영하는 분야입니다.

핵심 업무:
  • 수집(Ingestion): 다양한 소스로부터 데이터 획득
  • 저장(Storage): 데이터 레이크, 웨어하우스 설계
  • 변환(Transformation): ETL/ELT 파이프라인 구축
  • 제공(Serving): 분석·ML 시스템에 데이터 공급
""")

    # 샘플 데이터 생성으로 DE 역할 시연
    print_subheader("실습: 샘플 민원 데이터 수집 시뮬레이션")

    from sample_data_generator import PublicDataSimulator

    simulator = PublicDataSimulator(seed=42)
    sample_complaints = simulator.generate_batch(count=5)

    print("\n[수집된 민원 데이터 샘플]")
    for i, complaint in enumerate(sample_complaints, 1):
        print(f"  {i}. {complaint['complaint_id']}")
        print(f"     지역: {complaint['region_name']}")
        print(f"     유형: {complaint['issue_name']}")
        print(f"     시간: {complaint['event_time'][:19]}")


def section_2_mlops():
    """1.2 MLOps의 정의와 역할"""
    print_header("1.2 MLOps의 정의와 역할")

    print("""
MLOps는 ML 모델의 개발, 배포, 모니터링, 재학습을 체계적으로
관리하는 방법론입니다. DevOps 원칙을 ML에 적용한 것입니다.

핵심 단계:
  • 개발(Development): 실험, 피처 엔지니어링, 모델 훈련
  • 배포(Deployment): 모델 서빙, A/B 테스트
  • 모니터링(Monitoring): 성능 추적, 드리프트 감지
  • 재학습(Retraining): 자동화된 모델 갱신
""")

    print_subheader("공공 영역 MLOps 예시")
    print("""
[시나리오] 실시간 재난 긴급도 예측 시스템

1. 개발 단계:
   - 과거 재난 데이터로 긴급도 분류 모델 훈련
   - MLflow로 실험 추적 (정확도: 92%)

2. 배포 단계:
   - FastAPI로 REST API 구축
   - Kubernetes에 배포, 카나리 배포로 안전하게 전환

3. 모니터링 단계:
   - 예측 분포 실시간 모니터링
   - 계절적 패턴 변화 감지 (겨울철 한파 관련 재난 증가)

4. 재학습 단계:
   - 드리프트 감지 시 자동 재학습 파이프라인 트리거
   - 새 모델 Staging 배포 → 검증 → Production 승격
""")


def section_3_relationship():
    """1.3 DE와 MLOps의 관계"""
    print_header("1.3 DE와 MLOps의 관계")

    import pandas as pd

    comparison_data = {
        "구분": ["주요 산출물", "핵심 관심사", "주요 도구", "중첩 영역"],
        "데이터 엔지니어링": [
            "데이터 파이프라인, 피처",
            "데이터 품질, 가용성",
            "Kafka, Spark, Airflow",
            "피처 스토어, 데이터 품질 모니터링"
        ],
        "MLOps": [
            "모델, 예측 서비스",
            "모델 성능, 안정성",
            "MLflow, Kubeflow, Seldon",
            "피처 스토어, 데이터 품질 모니터링"
        ]
    }

    df = pd.DataFrame(comparison_data)
    print("\n[DE vs MLOps 비교]")
    print(df.to_string(index=False))

    print("""

[통합이 필요한 이유]
공공 데이터 프로젝트의 80%가 데이터 준비 단계에서 실패합니다.
DE 없이 MLOps는 "쓰레기 입력-쓰레기 출력(GIGO)" 문제에 직면합니다.

성공적인 공공 AI 시스템 = 견고한 DE 기반 + 체계적인 MLOps
""")


def section_4_public_sector():
    """1.4 공공 영역 특수성"""
    print_header("1.4 공공 영역 특수성")

    print("""
공공 영역 DE-MLOps는 다음 특수 요구사항을 갖습니다:

┌─────────────────────────────────────────────────────────────┐
│  1. 규제 준수                                                │
│     • 개인정보보호법: 민원인 정보 익명화 필수                    │
│     • 공공데이터법: 데이터 개방 및 품질 관리 의무                 │
├─────────────────────────────────────────────────────────────┤
│  2. 감사 추적                                                │
│     • 모든 데이터 처리 이력 기록 의무                           │
│     • 최소 3년 보관 (공공기록물법)                              │
│     • 감사원/국회 요청 시 즉시 제출 가능해야 함                   │
├─────────────────────────────────────────────────────────────┤
│  3. 투명성                                                   │
│     • 시민 대상 AI 의사결정 설명 가능성                          │
│     • 알고리즘 편향성 검증 및 공개                               │
│     • 모델 카드 작성 의무화 추세                                 │
├─────────────────────────────────────────────────────────────┤
│  4. 예산 제약                                                │
│     • 연간 예산 내 운영 (유연성 낮음)                            │
│     • 비용 효율적 아키텍처 설계 필수                             │
│     • 클라우드 비용 최적화 중요                                  │
└─────────────────────────────────────────────────────────────┘
""")


def section_5_practical_exercise():
    """실습 1.1: 공공데이터포털 API 호출"""
    print_header("실습 1.1: 공공데이터포털 API 호출")

    from public_data_client import PublicDataClient
    import json

    print("""
[실습 목표]
공공데이터포털 API를 호출하여 데이터를 수집하고 분석합니다.
실제 API 키가 없는 경우 시뮬레이터를 사용합니다.
""")

    # 클라이언트 초기화
    client = PublicDataClient(api_key=None, use_simulator=True)

    print_subheader("Step 1: 클라이언트 초기화")
    stats = client.get_stats()
    print(f"  API 키 설정: {stats['api_key_configured']}")
    print(f"  시뮬레이터 활성화: {stats['simulator_enabled']}")

    print_subheader("Step 2: 민원 데이터 조회")
    response = client.fetch_complaints(per_page=10)
    print(f"  성공 여부: {response.success}")
    print(f"  데이터 소스: {response.source.value}")
    print(f"  조회 건수: {response.total_count}")

    print_subheader("Step 3: 첫 번째 레코드 상세")
    if response.data:
        first_record = response.data[0]
        print(json.dumps(first_record, indent=2, ensure_ascii=False))

    print_subheader("Step 4: 지역별 통계")
    region_counts = {}
    for record in response.data:
        region = record.get("region_name", "Unknown")
        region_counts[region] = region_counts.get(region, 0) + 1

    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"  {region:10s}: {bar} ({count}건)")

    print_subheader("Step 5: 민원 유형별 통계")
    issue_counts = {}
    for record in response.data:
        issue = record.get("issue_name", "Unknown")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"  {issue:15s}: {bar} ({count}건)")


def section_6_pipeline_diagram():
    """실시간 데이터 파이프라인 도식화"""
    print_header("실시간 데이터 파이프라인 기본 구조")

    print("""
[공공 데이터 파이프라인 아키텍처]

┌──────────────┐     ┌──────────┐     ┌────────────────┐     ┌────────────┐
│  데이터 소스   │     │   수집    │     │      처리       │     │    서빙     │
├──────────────┤     ├──────────┤     ├────────────────┤     ├────────────┤
│              │     │          │     │                │     │            │
│  민원 API    │────▶│  Kafka   │────▶│ Spark Streaming│────▶│ ML 모델    │
│              │     │          │     │                │     │            │
│  재난 API    │────▶│ (이벤트  │     │   (실시간)      │     │ (추론)     │
│              │     │   버스)  │     │                │     │            │
│  교통 센서   │────▶│          │────▶│  Spark Batch   │────▶│ 대시보드   │
│              │     │          │     │                │     │            │
└──────────────┘     └──────────┘     │   (배치)       │     │ (Grafana)  │
                                      └────────────────┘     └────────────┘
                                              │
                                              ▼
                                      ┌────────────────┐
                                      │     저장       │
                                      ├────────────────┤
                                      │ 피처 스토어    │
                                      │ (Feast)       │
                                      │               │
                                      │ 데이터 레이크  │
                                      │ (S3/HDFS)    │
                                      └────────────────┘
""")

    # 다이어그램 이미지 생성
    print_subheader("다이어그램 이미지 생성")

    try:
        from pipeline_visualizer import PipelineVisualizer
        import matplotlib
        matplotlib.use('Agg')  # GUI 없이 실행

        output_dir = os.path.join(os.path.dirname(__file__), "outputs")
        os.makedirs(output_dir, exist_ok=True)

        visualizer = PipelineVisualizer()

        # 기본 파이프라인
        visualizer.create_basic_pipeline(
            save_path=os.path.join(output_dir, "basic_pipeline.png")
        )

        # DE vs MLOps 비교
        visualizer.create_de_mlops_comparison(
            save_path=os.path.join(output_dir, "de_mlops_comparison.png")
        )

        # 공공 영역 요구사항
        visualizer.create_public_sector_requirements(
            save_path=os.path.join(output_dir, "public_sector_requirements.png")
        )

        print(f"\n  다이어그램이 {output_dir}에 저장되었습니다:")
        for f in os.listdir(output_dir):
            if f.endswith('.png'):
                print(f"    - {f}")

    except Exception as e:
        print(f"  [경고] 다이어그램 생성 실패: {e}")
        print("  matplotlib가 설치되어 있는지 확인하세요.")


def section_7_exercises():
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
    print("##   Chapter 1: 데이터 엔지니어링과 MLOps의 개요" + " " * 19 + "##")
    print("##" + " " * 66 + "##")
    print("##   실습 난이도: ★☆☆☆☆" + " " * 41 + "##")
    print("##" + " " * 66 + "##")
    print("#" * 70)
    print("#" * 70)

    print(f"\n실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    # 각 섹션 실행
    section_1_data_engineering()
    section_2_mlops()
    section_3_relationship()
    section_4_public_sector()
    section_5_practical_exercise()
    section_6_pipeline_diagram()
    section_7_exercises()

    # 완료
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("Chapter 1 실습 완료!")
    print("=" * 70)
    print(f"  시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  소요 시간: {duration:.2f}초")
    print("\n[다음 단계]")
    print("  Chapter 2: 공공 실시간 데이터셋 이해로 이동하세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
