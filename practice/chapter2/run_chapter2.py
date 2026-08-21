#!/usr/bin/env python3
"""
Chapter 2: 공공 실시간 데이터셋 이해
====================================

이 스크립트는 Chapter 2의 모든 실습을 순차적으로 실행합니다.

학습 목표:
- 공공 실시간 데이터의 특성(형식, 유입 패턴, 품질 이슈)을 분류할 수 있다.
- JSON 기반 이벤트 로그 구조를 파싱하고 탐색적 분석을 수행할 수 있다.
- 데이터 드리프트 개념을 이해하고 공공 데이터 맥락에서 식별할 수 있다.

실습 난이도: ★★☆☆☆
"""

import sys
import os
from datetime import datetime, timedelta
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


def section_1_data_types():
    """2.1 공공 실시간 데이터의 유형"""
    print_header("2.1 공공 실시간 데이터의 유형")

    from data_types import print_data_type_summary, PublicDataGenerator, DataCategory

    print_data_type_summary()

    print_subheader("샘플 데이터 생성")

    generator = PublicDataGenerator(seed=42)

    # 각 유형별 샘플 생성
    for category in [DataCategory.COMPLAINT, DataCategory.DISASTER,
                     DataCategory.TRAFFIC, DataCategory.ENVIRONMENT]:
        print(f"\n[{category.value.upper()}]")
        if category == DataCategory.COMPLAINT:
            sample = generator.generate_complaint()
        elif category == DataCategory.DISASTER:
            sample = generator.generate_disaster()
        elif category == DataCategory.TRAFFIC:
            sample = generator.generate_traffic()
        else:
            sample = generator.generate_environment()

        # 주요 필드만 출력
        for key, value in list(sample.items())[:5]:
            print(f"  {key}: {value}")


def section_2_data_quality():
    """2.2 데이터 품질 이슈"""
    print_header("2.2 데이터 품질 이슈")

    print("""
공공 데이터에서 발생하는 주요 품질 이슈:

┌──────────────┬─────────────────────────────┬──────────────────────────┐
│   이슈 유형   │           설명              │       공공 데이터 예시      │
├──────────────┼─────────────────────────────┼──────────────────────────┤
│    중복      │ 동일 이벤트 다중 기록          │ 민원 재전송, 센서 중복 송신   │
├──────────────┼─────────────────────────────┼──────────────────────────┤
│    지연      │ 이벤트 발생-수신 시간차        │ 네트워크 장애 시 배치 도착   │
├──────────────┼─────────────────────────────┼──────────────────────────┤
│   불일치     │ 스키마/값 불일치              │ 지자체별 코드 체계 상이     │
├──────────────┼─────────────────────────────┼──────────────────────────┤
│    결측      │ 필수 필드 누락               │ 센서 오작동, API 오류       │
└──────────────┴─────────────────────────────┴──────────────────────────┘
""")

    print_subheader("품질 검증 데모")

    from data_types import PublicDataGenerator, DataCategory
    from data_quality import DataQualityReport
    import pandas as pd

    generator = PublicDataGenerator(seed=42)
    complaints = generator.generate_batch(DataCategory.COMPLAINT, count=200)

    # 의도적으로 품질 이슈 추가
    complaints.extend(complaints[:5])  # 중복
    for i in range(3):
        complaints[i]["region_code"] = None  # 결측

    df = pd.DataFrame(complaints)

    report = DataQualityReport(df)
    report.run_all_checks(
        key_columns=["event_time", "citizen_id"],
        time_column="event_time",
    )
    report.print_report()


def section_3_data_drift():
    """2.3 데이터 드리프트"""
    print_header("2.3 데이터 드리프트")

    print("""
데이터 드리프트: 시간에 따른 데이터 분포 변화

공공 데이터에서 발생 원인:
  1. 정책 변화: 새 민원 유형 신설
  2. 계절성: 동절기 난방 민원 증가
  3. 외부 이벤트: 재난 발생 시 관련 민원 급증
  4. 시스템 변경: API 스키마 변경
""")

    print_subheader("드리프트 감지 데모")

    from drift_detector import (
        KSTestDriftDetector, PSIDriftDetector, DriftVisualizer,
        create_drift_scenario
    )

    scenarios = create_drift_scenario()

    ks_detector = KSTestDriftDetector()
    psi_detector = PSIDriftDetector()

    results_summary = []

    for name, data in scenarios.items():
        baseline = data["baseline"]
        current = data["current"]

        ks_result = ks_detector.detect(baseline, current, "metric")
        psi_result = psi_detector.detect(baseline, current, "metric")

        results_summary.append({
            "시나리오": name,
            "KS p-value": f"{ks_result.p_value:.4f}",
            "PSI": f"{psi_result.statistic:.4f}",
            "드리프트": "예" if ks_result.is_drifted else "아니오",
        })

    import pandas as pd
    print("\n[드리프트 감지 결과 요약]")
    print(pd.DataFrame(results_summary).to_string(index=False))

    # 가장 심각한 드리프트 시각화
    print("\n[외부 이벤트 시나리오 분포 비교]")
    event_data = scenarios["외부 이벤트 (분포 변화)"]
    DriftVisualizer.print_distribution_comparison(
        event_data["baseline"],
        event_data["current"],
        "metric"
    )


def section_4_practical_exercise():
    """실습 2.1 & 2.2"""
    print_header("실습 2.1: 실시간 API 데이터 파싱")

    from data_types import PublicDataGenerator, DataCategory
    from json_parser import JSONEventParser, EDAReport
    import pandas as pd

    print("[데이터 수집 및 파싱]")

    generator = PublicDataGenerator(seed=42)
    complaints = generator.generate_batch(
        DataCategory.COMPLAINT,
        count=500,
        start_date=datetime.now() - timedelta(days=7)
    )

    parser = JSONEventParser()
    df = parser.parse_batch(complaints)

    print(f"  수집 건수: {len(df)}")
    print(f"  기간: {df['_parsed_time'].min()} ~ {df['_parsed_time'].max()}")

    print_subheader("탐색적 데이터 분석 (EDA)")

    report = EDAReport(df)
    report.print_report()


def section_5_exercises():
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
    print("##   Chapter 2: 공공 실시간 데이터셋 이해" + " " * 24 + "##")
    print("##" + " " * 66 + "##")
    print("##   실습 난이도: ★★☆☆☆" + " " * 40 + "##")
    print("##" + " " * 66 + "##")
    print("#" * 70)
    print("#" * 70)

    print(f"\n실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    # 각 섹션 실행
    section_1_data_types()
    section_2_data_quality()
    section_3_data_drift()
    section_4_practical_exercise()
    section_5_exercises()

    # 완료
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("Chapter 2 실습 완료!")
    print("=" * 70)
    print(f"  시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  소요 시간: {duration:.2f}초")
    print("\n[다음 단계]")
    print("  Chapter 3: 데이터 파이프라인 아키텍처 설계로 이동하세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
