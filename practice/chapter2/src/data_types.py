"""
공공 실시간 데이터 유형 분석

2.1 공공 실시간 데이터의 유형
- 민원 데이터
- 재난·안전 데이터
- 교통 데이터
- 환경 데이터
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Generator
from dataclasses import dataclass, field
from enum import Enum
import json


class DataCategory(Enum):
    """공공 데이터 카테고리"""
    COMPLAINT = "complaint"      # 민원
    DISASTER = "disaster"        # 재난·안전
    TRAFFIC = "traffic"          # 교통
    ENVIRONMENT = "environment"  # 환경


@dataclass
class DataTypeSpec:
    """데이터 유형 명세"""
    category: DataCategory
    source: str
    format: str
    volume: str  # 일일 유입량
    characteristics: List[str]
    sample_fields: List[str]
    quality_issues: List[str]


# 공공 데이터 유형 정의
PUBLIC_DATA_TYPES = {
    DataCategory.COMPLAINT: DataTypeSpec(
        category=DataCategory.COMPLAINT,
        source="국민신문고, 지자체 민원 시스템",
        format="JSON 이벤트 로그",
        volume="수십만~수백만 건/일",
        characteristics=[
            "비정형 텍스트 포함",
            "개인정보 마스킹 필요",
            "시간대별 패턴 존재 (업무 시간 집중)",
            "계절/이벤트별 유형 변동",
        ],
        sample_fields=[
            "event_time", "citizen_id", "issue_type",
            "region_code", "content_length", "attachments"
        ],
        quality_issues=[
            "중복 접수 (재전송)",
            "불완전한 필드 (선택 항목 누락)",
            "비표준 지역 코드",
        ],
    ),
    DataCategory.DISASTER: DataTypeSpec(
        category=DataCategory.DISASTER,
        source="재난안전데이터공유플랫폼",
        format="JSON/XML 실시간 피드",
        volume="이벤트 발생 시 버스트",
        characteristics=[
            "긴급도 분류 필요",
            "시계열 패턴",
            "지리 정보 포함",
            "다중 소스 통합",
        ],
        sample_fields=[
            "alert_id", "disaster_type", "severity",
            "location", "affected_population", "response_status"
        ],
        quality_issues=[
            "중복 경보",
            "위치 정보 오류",
            "심각도 불일치",
        ],
    ),
    DataCategory.TRAFFIC: DataTypeSpec(
        category=DataCategory.TRAFFIC,
        source="ITS(지능형교통시스템), 고속도로공사",
        format="센서 데이터 스트림",
        volume="초당 수천 건",
        characteristics=[
            "고빈도 (1초 미만 간격)",
            "위치 기반",
            "실시간 집계 필요",
            "계절/시간대 패턴",
        ],
        sample_fields=[
            "sensor_id", "timestamp", "speed",
            "volume", "occupancy", "road_section"
        ],
        quality_issues=[
            "센서 오작동",
            "통신 지연",
            "결측 구간",
        ],
    ),
    DataCategory.ENVIRONMENT: DataTypeSpec(
        category=DataCategory.ENVIRONMENT,
        source="에어코리아, 기상청",
        format="시계열 측정값",
        volume="분 단위 갱신",
        characteristics=[
            "정기적 갱신 주기",
            "측정 단위 표준화",
            "이상치 빈번",
            "계절성 강함",
        ],
        sample_fields=[
            "station_id", "measured_at", "pm25",
            "pm10", "o3", "temperature", "humidity"
        ],
        quality_issues=[
            "측정 장비 오류",
            "결측치 빈번",
            "단위 불일치",
        ],
    ),
}


class PublicDataGenerator:
    """공공 데이터 시뮬레이터"""

    def __init__(self, seed: int = None):
        if seed:
            random.seed(seed)
        self.region_codes = ["11", "26", "27", "28", "41", "42", "43", "44", "45", "46", "47", "48"]

    def generate_complaint(self, event_time: datetime = None) -> Dict[str, Any]:
        """민원 데이터 생성"""
        if event_time is None:
            event_time = datetime.now()

        issue_types = [
            "noise_complaint", "road_repair", "illegal_parking",
            "streetlight", "waste_disposal", "water_supply",
            "public_facility", "traffic_signal", "park_maintenance"
        ]

        return {
            "event_time": event_time.isoformat() + "Z",
            "event_type": "complaint",
            "citizen_id": f"MASKED_{random.randint(10000, 99999)}",
            "issue_type": random.choice(issue_types),
            "region_code": random.choice(self.region_codes),
            "content_length": random.randint(50, 500),
            "attachments": random.choices([0, 1, 2, 3], weights=[0.4, 0.35, 0.2, 0.05])[0],
            "priority": random.choices(
                ["low", "medium", "high", "urgent"],
                weights=[0.3, 0.45, 0.2, 0.05]
            )[0],
        }

    def generate_disaster(self, event_time: datetime = None) -> Dict[str, Any]:
        """재난 데이터 생성"""
        if event_time is None:
            event_time = datetime.now()

        disaster_types = ["fire", "flood", "earthquake", "typhoon", "traffic_accident", "gas_leak"]

        return {
            "alert_id": f"DST-{event_time.strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}",
            "event_time": event_time.isoformat() + "Z",
            "disaster_type": random.choice(disaster_types),
            "severity": random.choices(
                ["1_minor", "2_moderate", "3_significant", "4_severe", "5_critical"],
                weights=[0.4, 0.3, 0.15, 0.1, 0.05]
            )[0],
            "location": {
                "latitude": round(random.uniform(33.0, 38.5), 6),
                "longitude": round(random.uniform(124.5, 131.5), 6),
            },
            "affected_population": random.randint(0, 10000),
            "response_status": random.choice(["pending", "dispatched", "on_scene", "resolved"]),
        }

    def generate_traffic(self, event_time: datetime = None) -> Dict[str, Any]:
        """교통 데이터 생성"""
        if event_time is None:
            event_time = datetime.now()

        # 시간대에 따른 교통량 시뮬레이션
        hour = event_time.hour
        if 7 <= hour <= 9 or 17 <= hour <= 19:  # 출퇴근 시간
            base_speed = random.randint(20, 50)
            base_volume = random.randint(1500, 2500)
        elif 0 <= hour <= 5:  # 심야
            base_speed = random.randint(80, 100)
            base_volume = random.randint(100, 500)
        else:
            base_speed = random.randint(50, 80)
            base_volume = random.randint(800, 1500)

        return {
            "sensor_id": f"SENSOR_{random.randint(1, 1000):04d}",
            "timestamp": event_time.isoformat() + "Z",
            "road_section": f"SEC_{random.randint(1, 100):03d}",
            "speed": base_speed + random.randint(-10, 10),
            "volume": base_volume + random.randint(-200, 200),
            "occupancy": round(random.uniform(0.1, 0.9), 2),
            "lane_count": random.choice([2, 3, 4]),
        }

    def generate_environment(self, event_time: datetime = None) -> Dict[str, Any]:
        """환경 데이터 생성"""
        if event_time is None:
            event_time = datetime.now()

        # 계절에 따른 미세먼지 시뮬레이션
        month = event_time.month
        if month in [3, 4, 5]:  # 봄 (황사)
            pm25_base = random.randint(30, 80)
            pm10_base = random.randint(50, 150)
        elif month in [12, 1, 2]:  # 겨울 (난방)
            pm25_base = random.randint(25, 60)
            pm10_base = random.randint(40, 100)
        else:
            pm25_base = random.randint(10, 40)
            pm10_base = random.randint(20, 70)

        return {
            "station_id": f"STN_{random.randint(1, 500):03d}",
            "measured_at": event_time.isoformat() + "Z",
            "pm25": pm25_base + random.randint(-5, 10),
            "pm10": pm10_base + random.randint(-10, 20),
            "o3": round(random.uniform(0.01, 0.08), 3),
            "co": round(random.uniform(0.3, 1.0), 2),
            "no2": round(random.uniform(0.01, 0.05), 3),
            "temperature": round(random.uniform(-10, 35), 1),
            "humidity": random.randint(30, 90),
        }

    def generate_batch(self, category: DataCategory, count: int = 100,
                       start_date: datetime = None, end_date: datetime = None) -> List[Dict]:
        """배치 데이터 생성"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()

        generators = {
            DataCategory.COMPLAINT: self.generate_complaint,
            DataCategory.DISASTER: self.generate_disaster,
            DataCategory.TRAFFIC: self.generate_traffic,
            DataCategory.ENVIRONMENT: self.generate_environment,
        }

        generator = generators.get(category)
        if not generator:
            raise ValueError(f"Unknown category: {category}")

        records = []
        time_range = (end_date - start_date).total_seconds()

        for _ in range(count):
            random_seconds = random.random() * time_range
            event_time = start_date + timedelta(seconds=random_seconds)
            records.append(generator(event_time))

        # 시간순 정렬
        records.sort(key=lambda x: x.get("event_time") or x.get("timestamp") or x.get("measured_at"))
        return records


def print_data_type_summary():
    """데이터 유형 요약 출력"""
    print("=" * 70)
    print("공공 실시간 데이터 유형 요약")
    print("=" * 70)

    for category, spec in PUBLIC_DATA_TYPES.items():
        print(f"\n[{category.value.upper()}] {spec.source}")
        print("-" * 50)
        print(f"  형식: {spec.format}")
        print(f"  유입량: {spec.volume}")
        print(f"  주요 특성:")
        for char in spec.characteristics:
            print(f"    • {char}")
        print(f"  품질 이슈:")
        for issue in spec.quality_issues:
            print(f"    ⚠ {issue}")


def demo():
    """데모 실행"""
    print_data_type_summary()

    print("\n" + "=" * 70)
    print("샘플 데이터 생성")
    print("=" * 70)

    generator = PublicDataGenerator(seed=42)

    for category in DataCategory:
        print(f"\n[{category.value.upper()}] 샘플 레코드:")
        records = generator.generate_batch(category, count=2)
        for record in records:
            print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    demo()
