"""
Chapter 1 연습 문제 해답

연습 문제:
1. (이해) DE와 MLOps가 중첩되는 영역 3가지를 나열하고, 각각 공공 영역 사례를 들어 설명하라.
2. (분석) 민간 기업과 공공 기관의 DE-MLOps 요구사항 차이를 표로 정리하라.
3. (적용) 본인이 속한 지역의 공공데이터 포털에서 실시간 API를 1개 찾아 문서화하라.
"""

import pandas as pd
from datetime import datetime
import json


def exercise_1_overlapping_areas():
    """
    연습 문제 1: DE와 MLOps가 중첩되는 영역

    학습 목표: DE와 MLOps의 관계를 이해하고 통합의 필요성을 설명할 수 있다.
    """
    print("=" * 70)
    print("연습 문제 1: DE와 MLOps 중첩 영역")
    print("=" * 70)

    overlapping_areas = [
        {
            "영역": "피처 스토어 (Feature Store)",
            "DE 역할": "피처 파이프라인 구축, 데이터 변환, 저장소 관리",
            "MLOps 역할": "피처 버전 관리, 훈련-서빙 일관성 보장",
            "공공 사례": "민원 분류 모델을 위한 '지역별 민원 발생 건수', "
                        "'최근 7일 민원 유형 분포' 등의 피처를 중앙 저장소에서 관리. "
                        "여러 부서의 모델이 동일한 피처를 재사용하여 중복 개발 방지."
        },
        {
            "영역": "데이터 품질 모니터링 (Data Quality Monitoring)",
            "DE 역할": "데이터 완전성, 정확성, 적시성 검증 파이프라인",
            "MLOps 역할": "모델 입력 데이터 검증, 드리프트 감지",
            "공공 사례": "실시간 교통 데이터의 품질 저하(센서 오류, 결측치 급증)를 "
                        "자동 감지하여 교통 예측 모델의 성능 저하 전에 알림. "
                        "데이터 품질 저하 시 모델 재학습 트리거."
        },
        {
            "영역": "메타데이터 관리 (Metadata Management)",
            "DE 역할": "데이터 리니지, 스키마 관리, 데이터 카탈로그",
            "MLOps 역할": "모델 리니지, 실험 추적, 모델 카드",
            "공공 사례": "재난 예측 모델이 어떤 데이터로 훈련되었는지 추적 가능. "
                        "감사 요청 시 특정 시점의 모델이 사용한 데이터셋, "
                        "전처리 과정, 하이퍼파라미터 등 전체 이력 제공."
        },
    ]

    # 결과 출력
    for i, area in enumerate(overlapping_areas, 1):
        print(f"\n{i}. {area['영역']}")
        print("-" * 50)
        print(f"   [DE 역할] {area['DE 역할']}")
        print(f"   [MLOps 역할] {area['MLOps 역할']}")
        print(f"   [공공 사례] {area['공공 사례']}")

    return overlapping_areas


def exercise_2_comparison_table():
    """
    연습 문제 2: 민간 vs 공공 DE-MLOps 요구사항 비교

    학습 목표: 공공 영역의 특수 요구사항을 이해한다.
    """
    print("\n" + "=" * 70)
    print("연습 문제 2: 민간 기업 vs 공공 기관 요구사항 비교")
    print("=" * 70)

    comparison_data = {
        "구분": [
            "주요 목표",
            "성공 지표",
            "데이터 규제",
            "투명성",
            "예산",
            "의사결정 속도",
            "기술 스택",
            "실패 허용도",
            "감사 요구",
            "사용자",
        ],
        "민간 기업": [
            "수익 극대화, 비용 절감",
            "매출, 전환율, 고객 만족도",
            "GDPR, 개인정보보호법 (상대적 유연)",
            "내부 이해관계자 중심",
            "ROI 기반 유동적 투자",
            "빠름 (Agile, 실험 중심)",
            "최신 기술 적극 도입",
            "빠른 실패, 빠른 학습",
            "내부 감사, 규제 기관",
            "고객, 내부 직원",
        ],
        "공공 기관": [
            "공공 서비스 품질 향상, 행정 효율화",
            "시민 만족도, 처리 시간, 비용 효율",
            "개인정보보호법, 공공데이터법 (엄격)",
            "시민 대상 완전 공개 원칙",
            "연간 예산 고정, 승인 절차 복잡",
            "느림 (절차, 합의 중심)",
            "검증된 기술, 보안 인증 필수",
            "실패 비용 높음, 보수적 접근",
            "감사원, 국회, 시민 감시",
            "전체 시민, 공무원",
        ],
    }

    df = pd.DataFrame(comparison_data)
    print("\n" + df.to_string(index=False))

    # 핵심 차이점 요약
    print("\n[핵심 차이점 요약]")
    print("-" * 50)
    key_differences = [
        "1. 규제 강도: 공공은 법적 준수 의무가 더 엄격함",
        "2. 투명성: 공공은 시민에게 AI 의사결정 설명 의무",
        "3. 예산: 공공은 연간 예산 내 운영, 유연성 낮음",
        "4. 실패 허용도: 공공은 정치적 부담으로 보수적",
        "5. 감사: 공공은 외부 감사 대응 체계 필수",
    ]
    for diff in key_differences:
        print(f"   {diff}")

    return df


def exercise_3_api_documentation():
    """
    연습 문제 3: 공공데이터 API 문서화 예시

    학습 목표: 실제 공공데이터 API를 탐색하고 문서화할 수 있다.
    """
    print("\n" + "=" * 70)
    print("연습 문제 3: 공공데이터 API 문서화 예시")
    print("=" * 70)

    api_documentation = {
        "API 기본 정보": {
            "이름": "서울시 실시간 도시데이터 API",
            "제공처": "서울열린데이터광장 (data.seoul.go.kr)",
            "데이터 유형": "실시간 교통, 환경, 인구 데이터",
            "갱신 주기": "5분",
            "인증 방식": "API 키 (무료 발급)",
            "호출 제한": "1,000회/일",
        },
        "엔드포인트": {
            "기본 URL": "http://openapi.seoul.go.kr:8088",
            "형식": "/{API_KEY}/{응답형식}/{서비스명}/{시작위치}/{끝위치}",
            "예시": "/key/json/citydata/1/5/강남역",
        },
        "응답 필드": [
            {"필드명": "AREA_NM", "설명": "지역명", "타입": "string"},
            {"필드명": "AREA_CONGEST_LVL", "설명": "혼잡도 수준", "타입": "string"},
            {"필드명": "AREA_CONGEST_MSG", "설명": "혼잡도 메시지", "타입": "string"},
            {"필드명": "AREA_PPLTN_MIN", "설명": "추정 최소 인구", "타입": "integer"},
            {"필드명": "AREA_PPLTN_MAX", "설명": "추정 최대 인구", "타입": "integer"},
        ],
        "활용 사례": [
            "실시간 인파 밀집도 모니터링",
            "재난 대응 의사결정 지원",
            "도시 교통 정책 수립 기초 데이터",
        ],
        "주의사항": [
            "개인 식별 불가능한 집계 데이터만 제공",
            "실시간 데이터는 5분 지연 가능",
            "API 호출 제한 초과 시 서비스 중단",
        ],
    }

    # 출력
    print("\n[API 기본 정보]")
    for key, value in api_documentation["API 기본 정보"].items():
        print(f"   {key}: {value}")

    print("\n[엔드포인트]")
    for key, value in api_documentation["엔드포인트"].items():
        print(f"   {key}: {value}")

    print("\n[응답 필드]")
    for field in api_documentation["응답 필드"]:
        print(f"   - {field['필드명']} ({field['타입']}): {field['설명']}")

    print("\n[활용 사례]")
    for case in api_documentation["활용 사례"]:
        print(f"   - {case}")

    print("\n[주의사항]")
    for note in api_documentation["주의사항"]:
        print(f"   - {note}")

    # 샘플 호출 코드
    print("\n[샘플 호출 코드]")
    print("-" * 50)
    sample_code = '''
import requests

API_KEY = "YOUR_API_KEY"
AREA = "강남역"

url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/citydata/1/5/{AREA}"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    city_data = data.get("CITYDATA", {})

    print(f"지역: {city_data.get('AREA_NM')}")
    print(f"혼잡도: {city_data.get('AREA_CONGEST_LVL')}")
    print(f"추정 인구: {city_data.get('AREA_PPLTN_MIN')} ~ {city_data.get('AREA_PPLTN_MAX')}")
'''
    print(sample_code)

    return api_documentation


def run_all_exercises():
    """모든 연습 문제 실행"""
    print("\n" + "#" * 70)
    print("#" + " " * 20 + "Chapter 1 연습 문제 해답" + " " * 21 + "#")
    print("#" * 70)

    # 연습 문제 1
    result_1 = exercise_1_overlapping_areas()

    # 연습 문제 2
    result_2 = exercise_2_comparison_table()

    # 연습 문제 3
    result_3 = exercise_3_api_documentation()

    print("\n" + "=" * 70)
    print("모든 연습 문제 완료!")
    print("=" * 70)

    # 평가 기준 안내
    print("\n[평가 기준 참고]")
    print("-" * 50)
    print("""
등급 A: 모든 문제에 대해 구체적 사례와 근거 제시, 코드 실행 결과 포함
등급 B: 주요 개념 정확히 설명, 사례 1개 이상 제시
등급 C: 기본 개념 이해, 사례 없이 일반적 답변
등급 D: 개념 혼동 또는 불완전한 답변

위 해답은 등급 A 수준의 예시 답안입니다.
""")

    return {
        "exercise_1": result_1,
        "exercise_2": result_2,
        "exercise_3": result_3,
    }


if __name__ == "__main__":
    run_all_exercises()
