"""
샘플 공공데이터 생성기

실제 API 키가 없는 경우에도 실습할 수 있도록
현실적인 공공 민원 데이터를 시뮬레이션합니다.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json


class PublicDataSimulator:
    """공공 민원 데이터 시뮬레이터"""

    # 지역 코드 (시도)
    REGION_CODES = {
        "11": "서울특별시",
        "26": "부산광역시",
        "27": "대구광역시",
        "28": "인천광역시",
        "29": "광주광역시",
        "30": "대전광역시",
        "31": "울산광역시",
        "36": "세종특별자치시",
        "41": "경기도",
        "42": "강원도",
        "43": "충청북도",
        "44": "충청남도",
        "45": "전라북도",
        "46": "전라남도",
        "47": "경상북도",
        "48": "경상남도",
        "50": "제주특별자치도",
    }

    # 민원 유형
    ISSUE_TYPES = [
        ("noise_complaint", "소음 민원", 0.15),
        ("road_repair", "도로 보수", 0.12),
        ("illegal_parking", "불법 주정차", 0.18),
        ("streetlight", "가로등 고장", 0.08),
        ("waste_disposal", "쓰레기 무단투기", 0.10),
        ("water_supply", "수도 관련", 0.07),
        ("public_facility", "공공시설 관리", 0.09),
        ("traffic_signal", "신호등 고장", 0.05),
        ("park_maintenance", "공원 관리", 0.06),
        ("air_quality", "대기질 민원", 0.04),
        ("flooding", "침수 신고", 0.03),
        ("other", "기타", 0.03),
    ]

    # 시간대별 민원 발생 가중치 (0-23시)
    HOURLY_WEIGHTS = [
        0.2, 0.1, 0.1, 0.1, 0.1, 0.2,  # 0-5시
        0.4, 0.6, 0.8, 1.0, 1.2, 1.0,  # 6-11시
        0.9, 1.0, 1.2, 1.3, 1.2, 1.0,  # 12-17시
        0.9, 0.8, 0.7, 0.6, 0.4, 0.3,  # 18-23시
    ]

    def __init__(self, seed: int = None):
        if seed:
            random.seed(seed)

    def _weighted_choice(self, choices_with_weights):
        """가중치 기반 선택"""
        items = [item[0] for item in choices_with_weights]
        weights = [item[2] for item in choices_with_weights]
        return random.choices(items, weights=weights, k=1)[0]

    def _get_issue_name(self, issue_code: str) -> str:
        """민원 유형 코드로 한글명 반환"""
        for code, name, _ in self.ISSUE_TYPES:
            if code == issue_code:
                return name
        return "기타"

    def generate_complaint(self, base_time: datetime = None) -> Dict[str, Any]:
        """단일 민원 레코드 생성"""
        if base_time is None:
            base_time = datetime.now()

        # 시간대별 가중치 적용
        hour = base_time.hour
        if random.random() > self.HOURLY_WEIGHTS[hour]:
            # 해당 시간대에 민원이 덜 발생하도록
            base_time = base_time + timedelta(hours=random.randint(1, 4))

        region_code = random.choice(list(self.REGION_CODES.keys()))
        issue_type = self._weighted_choice(self.ISSUE_TYPES)

        return {
            "complaint_id": f"CMP-{base_time.strftime('%Y%m%d')}-{random.randint(10000, 99999)}",
            "event_time": base_time.isoformat() + "Z",
            "event_type": "complaint",
            "citizen_id": f"MASKED_ID_{random.randint(10000, 99999)}",
            "region_code": region_code,
            "region_name": self.REGION_CODES[region_code],
            "issue_type": issue_type,
            "issue_name": self._get_issue_name(issue_type),
            "content_length": random.randint(50, 500),
            "attachments": random.choices([0, 1, 2, 3], weights=[0.4, 0.35, 0.2, 0.05])[0],
            "priority": random.choices(["low", "medium", "high", "urgent"],
                                       weights=[0.3, 0.45, 0.2, 0.05])[0],
            "channel": random.choices(["web", "mobile", "phone", "visit"],
                                      weights=[0.4, 0.35, 0.2, 0.05])[0],
        }

    def generate_batch(self,
                       count: int = 100,
                       start_date: datetime = None,
                       end_date: datetime = None) -> List[Dict[str, Any]]:
        """배치 민원 데이터 생성"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()

        records = []
        time_range = (end_date - start_date).total_seconds()

        for _ in range(count):
            random_seconds = random.random() * time_range
            event_time = start_date + timedelta(seconds=random_seconds)
            records.append(self.generate_complaint(event_time))

        # 시간순 정렬
        records.sort(key=lambda x: x["event_time"])
        return records

    def generate_realtime_stream(self, duration_seconds: int = 60,
                                  avg_events_per_second: float = 0.5):
        """실시간 스트림 시뮬레이션 (제너레이터)"""
        import time

        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration_seconds)

        while datetime.now() < end_time:
            # 포아송 분포 기반 이벤트 발생
            if random.random() < avg_events_per_second:
                yield self.generate_complaint(datetime.now())
            time.sleep(0.1)  # 100ms 간격 체크


class DisasterDataSimulator:
    """재난 안전 데이터 시뮬레이터"""

    DISASTER_TYPES = [
        ("fire", "화재", 0.25),
        ("flood", "홍수/침수", 0.15),
        ("earthquake", "지진", 0.05),
        ("typhoon", "태풍", 0.10),
        ("heavy_snow", "폭설", 0.10),
        ("traffic_accident", "교통사고", 0.20),
        ("building_collapse", "건물붕괴", 0.03),
        ("gas_leak", "가스누출", 0.07),
        ("power_outage", "정전", 0.05),
    ]

    SEVERITY_LEVELS = ["1_minor", "2_moderate", "3_significant", "4_severe", "5_critical"]

    def __init__(self, seed: int = None):
        if seed:
            random.seed(seed)

    def generate_alert(self, base_time: datetime = None) -> Dict[str, Any]:
        """단일 재난 경보 생성"""
        if base_time is None:
            base_time = datetime.now()

        disaster_type = random.choices(
            [d[0] for d in self.DISASTER_TYPES],
            weights=[d[2] for d in self.DISASTER_TYPES]
        )[0]

        return {
            "alert_id": f"DST-{base_time.strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}",
            "event_time": base_time.isoformat() + "Z",
            "disaster_type": disaster_type,
            "severity": random.choices(
                self.SEVERITY_LEVELS,
                weights=[0.4, 0.3, 0.15, 0.1, 0.05]
            )[0],
            "location": {
                "latitude": round(random.uniform(33.0, 38.5), 6),
                "longitude": round(random.uniform(124.5, 131.5), 6),
            },
            "affected_population": random.randint(0, 10000),
            "response_status": random.choice(["pending", "dispatched", "on_scene", "resolved"]),
        }


def demo():
    """데모 실행"""
    print("=" * 60)
    print("공공 데이터 시뮬레이터 데모")
    print("=" * 60)

    # 민원 데이터 생성
    complaint_sim = PublicDataSimulator(seed=42)

    print("\n[1] 단일 민원 레코드 생성:")
    single_complaint = complaint_sim.generate_complaint()
    print(json.dumps(single_complaint, indent=2, ensure_ascii=False))

    print("\n[2] 배치 민원 데이터 생성 (10건):")
    batch_data = complaint_sim.generate_batch(count=10)
    for i, record in enumerate(batch_data[:3], 1):
        print(f"  {i}. {record['complaint_id']} - {record['issue_name']} ({record['region_name']})")
    print(f"  ... 외 {len(batch_data) - 3}건")

    # 재난 데이터 생성
    disaster_sim = DisasterDataSimulator(seed=42)

    print("\n[3] 재난 경보 데이터 생성:")
    alert = disaster_sim.generate_alert()
    print(json.dumps(alert, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("데모 완료")


if __name__ == "__main__":
    demo()
