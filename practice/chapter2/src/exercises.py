"""
Chapter 2 연습 문제 해답

연습 문제:
1. (이해) 공공 실시간 데이터 4가지 유형의 특성을 비교하는 표를 작성하라.
2. (분석) 민원 데이터에서 발생 가능한 드리프트 시나리오 3가지를 제시하고, 각각의 감지 방법을 설명하라.
3. (적용) 제공된 코드를 활용하여 공공데이터 API에서 데이터를 수집하고, 시간대별 분포를 시각화하라.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from data_types import PUBLIC_DATA_TYPES, DataCategory, PublicDataGenerator
from drift_detector import KSTestDriftDetector, PSIDriftDetector, DriftVisualizer


def exercise_1_data_type_comparison():
    """
    연습 문제 1: 공공 실시간 데이터 4가지 유형 비교

    학습 목표: 공공 실시간 데이터의 특성을 분류할 수 있다.
    """
    print("=" * 80)
    print("연습 문제 1: 공공 실시간 데이터 유형 비교표")
    print("=" * 80)

    # 비교표 데이터
    comparison_data = {
        "구분": ["민원", "재난·안전", "교통", "환경"],
        "소스": [
            "국민신문고, 지자체",
            "재난안전데이터플랫폼",
            "ITS, 고속도로공사",
            "에어코리아, 기상청"
        ],
        "형식": [
            "JSON 이벤트 로그",
            "JSON/XML 피드",
            "센서 스트림",
            "시계열 측정값"
        ],
        "유입량": [
            "수십만~수백만/일",
            "이벤트 발생 시 버스트",
            "초당 수천 건",
            "분 단위 갱신"
        ],
        "주요 특성": [
            "비정형 텍스트, 개인정보",
            "긴급도 분류, 지리정보",
            "고빈도, 위치 기반",
            "정기 갱신, 계절성"
        ],
        "품질 이슈": [
            "중복 접수, 필드 누락",
            "중복 경보, 위치 오류",
            "센서 오작동, 결측",
            "장비 오류, 이상치"
        ],
    }

    df = pd.DataFrame(comparison_data)
    print("\n" + df.to_string(index=False))

    # 추가 분석
    print("\n[유형별 ML 활용 사례]")
    print("-" * 60)
    use_cases = {
        "민원": "민원 유형 자동 분류, 처리 시간 예측, 급증 감지",
        "재난·안전": "재난 긴급도 예측, 대피 경로 최적화, 피해 규모 추정",
        "교통": "교통량 예측, 정체 구간 탐지, 신호 최적화",
        "환경": "대기질 예측, 이상치 탐지, 건강 영향 경보",
    }
    for data_type, use_case in use_cases.items():
        print(f"  • {data_type}: {use_case}")


def exercise_2_drift_scenarios():
    """
    연습 문제 2: 민원 데이터 드리프트 시나리오

    학습 목표: 데이터 드리프트 개념을 이해하고 식별할 수 있다.
    """
    print("\n" + "=" * 80)
    print("연습 문제 2: 민원 데이터 드리프트 시나리오")
    print("=" * 80)

    scenarios = [
        {
            "시나리오": "1. 정책 변화에 의한 드리프트",
            "설명": "새로운 민원 유형 신설 또는 기존 유형 통폐합으로 인한 분포 변화",
            "예시": "2026년 1월 '스마트시티 민원' 카테고리 신설로 기타 민원 감소",
            "감지_방법": "범주형 분포 모니터링 (Chi-square 검정)",
            "지표": "민원 유형별 비율의 변화, 새로운 카테고리 출현",
            "대응": "모델 피처 업데이트, 새 유형에 대한 학습 데이터 수집",
        },
        {
            "시나리오": "2. 계절성에 의한 드리프트",
            "설명": "계절에 따른 특정 민원 유형의 주기적 증감",
            "예시": "동절기 난방 민원 300% 증가, 하절기 냉방/악취 민원 급증",
            "감지_방법": "시계열 분해 (STL), PSI를 이용한 월별 분포 비교",
            "지표": "content_length 분포 변화, 특정 issue_type 비율 급변",
            "대응": "계절별 모델 운영 또는 계절 피처 추가",
        },
        {
            "시나리오": "3. 외부 이벤트에 의한 드리프트",
            "설명": "예상치 못한 사건(재난, 대규모 시위 등)으로 인한 급격한 패턴 변화",
            "예시": "코로나19 발생 후 방역 관련 민원 1000% 증가",
            "감지_방법": "KS 검정 + 이동 평균 대비 급증 탐지",
            "지표": "일일 접수량의 급격한 변화, 새로운 키워드 출현",
            "대응": "이상 탐지 시스템 알림, 모델 긴급 재학습 트리거",
        },
    ]

    for scenario in scenarios:
        print(f"\n[{scenario['시나리오']}]")
        print("-" * 60)
        print(f"  설명: {scenario['설명']}")
        print(f"  예시: {scenario['예시']}")
        print(f"  감지 방법: {scenario['감지_방법']}")
        print(f"  모니터링 지표: {scenario['지표']}")
        print(f"  대응 방안: {scenario['대응']}")

    # 실제 드리프트 감지 시연
    print("\n\n[드리프트 감지 시연]")
    print("=" * 60)

    np.random.seed(42)

    # 정상 기간 데이터 (baseline)
    baseline_content_length = np.random.normal(200, 50, 500)

    # 계절성 드리프트 시뮬레이션 (겨울철 - 내용이 길어짐)
    winter_content_length = np.random.normal(280, 60, 500)

    # 드리프트 감지
    ks_detector = KSTestDriftDetector()
    psi_detector = PSIDriftDetector()

    ks_result = ks_detector.detect(baseline_content_length, winter_content_length, "content_length")
    psi_result = psi_detector.detect(baseline_content_length, winter_content_length, "content_length")

    print("\n계절성 드리프트 감지 결과 (평상시 vs 동절기):")
    print(f"  KS 통계량: {ks_result.statistic}, p-value: {ks_result.p_value}")
    print(f"  드리프트 여부: {'감지됨 ⚠️' if ks_result.is_drifted else '정상'}")
    print(f"  PSI: {psi_result.statistic} ({psi_result.details['psi_interpretation']})")

    # 분포 비교 시각화
    DriftVisualizer.print_distribution_comparison(
        baseline_content_length, winter_content_length, "content_length"
    )


def exercise_3_temporal_visualization():
    """
    연습 문제 3: 시간대별 분포 시각화

    학습 목표: JSON 데이터를 파싱하고 탐색적 분석을 수행할 수 있다.
    """
    print("\n" + "=" * 80)
    print("연습 문제 3: 시간대별 분포 시각화")
    print("=" * 80)

    # 데이터 생성
    generator = PublicDataGenerator(seed=42)
    complaints = generator.generate_batch(
        DataCategory.COMPLAINT,
        count=1000,
        start_date=datetime.now() - timedelta(days=7),
        end_date=datetime.now()
    )

    df = pd.DataFrame(complaints)
    df['event_time'] = pd.to_datetime(df['event_time'])
    df['hour'] = df['event_time'].dt.hour
    df['day_of_week'] = df['event_time'].dt.dayofweek
    df['date'] = df['event_time'].dt.date

    # 시간대별 분포
    print("\n[1. 시간대별 민원 접수 분포]")
    print("-" * 60)

    hourly_counts = df.groupby('hour').size()
    max_count = hourly_counts.max()

    for hour in range(24):
        count = hourly_counts.get(hour, 0)
        bar_len = int(count / max_count * 40)
        bar = "█" * bar_len

        # 시간대 구분
        if 0 <= hour < 6:
            period = "심야"
        elif 6 <= hour < 9:
            period = "출근"
        elif 9 <= hour < 12:
            period = "오전"
        elif 12 <= hour < 14:
            period = "점심"
        elif 14 <= hour < 18:
            period = "오후"
        elif 18 <= hour < 21:
            period = "저녁"
        else:
            period = "야간"

        print(f"  {hour:02d}시 [{period}]: {bar} ({count})")

    # 피크 시간 분석
    peak_hours = hourly_counts.nlargest(3)
    print(f"\n  피크 시간대: ", end="")
    print(", ".join([f"{h}시({c}건)" for h, c in peak_hours.items()]))

    # 요일별 분포
    print("\n[2. 요일별 민원 접수 분포]")
    print("-" * 60)

    weekday_names = ['월', '화', '수', '목', '금', '토', '일']
    daily_counts = df.groupby('day_of_week').size()

    for dow in range(7):
        count = daily_counts.get(dow, 0)
        bar = "█" * int(count / daily_counts.max() * 30)
        day_type = "평일" if dow < 5 else "주말"
        print(f"  {weekday_names[dow]}요일 [{day_type}]: {bar} ({count})")

    # 민원 유형별 분포
    print("\n[3. 민원 유형별 분포]")
    print("-" * 60)

    issue_counts = df['issue_type'].value_counts()
    for issue_type, count in issue_counts.items():
        pct = count / len(df) * 100
        bar = "█" * int(pct * 2)
        print(f"  {issue_type:20s}: {bar} ({count}건, {pct:.1f}%)")

    # 지역별 분포
    print("\n[4. 지역별 민원 분포 (상위 5)]")
    print("-" * 60)

    region_counts = df['region_code'].value_counts().head(5)
    region_names = {
        "11": "서울", "26": "부산", "27": "대구", "28": "인천",
        "41": "경기", "42": "강원", "43": "충북", "44": "충남",
    }
    for region_code, count in region_counts.items():
        region_name = region_names.get(region_code, region_code)
        bar = "█" * int(count / region_counts.max() * 25)
        print(f"  {region_name} ({region_code}): {bar} ({count})")


def run_all_exercises():
    """모든 연습 문제 실행"""
    print("\n" + "#" * 80)
    print("#" + " " * 25 + "Chapter 2 연습 문제 해답" + " " * 26 + "#")
    print("#" * 80)

    exercise_1_data_type_comparison()
    exercise_2_drift_scenarios()
    exercise_3_temporal_visualization()

    print("\n" + "=" * 80)
    print("모든 연습 문제 완료!")
    print("=" * 80)

    print("\n[평가 기준 참고]")
    print("-" * 60)
    print("""
등급 A: 드리프트 시나리오에 통계적 감지 방법 명시, 시각화 결과 해석 포함
등급 B: 드리프트 개념 정확히 이해, 기본 분석 수행
등급 C: 데이터 유형 구분 가능, 코드 실행 성공
등급 D: 개념 혼동 또는 코드 실행 실패

위 해답은 등급 A 수준의 예시 답안입니다.
""")


if __name__ == "__main__":
    run_all_exercises()
