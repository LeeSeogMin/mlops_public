"""
공공데이터 API 클라이언트

공공데이터포털(data.go.kr) API 호출을 위한 클라이언트입니다.
실제 API 키가 없는 경우 시뮬레이터로 대체합니다.
"""

import requests
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# 시뮬레이터 임포트 (API 키 없을 때 사용)
try:
    from .sample_data_generator import PublicDataSimulator, DisasterDataSimulator
except ImportError:
    from sample_data_generator import PublicDataSimulator, DisasterDataSimulator


class DataSource(Enum):
    """데이터 소스 유형"""
    REAL_API = "real_api"
    SIMULATOR = "simulator"


@dataclass
class APIResponse:
    """API 응답 표준 구조"""
    success: bool
    data: List[Dict[str, Any]]
    total_count: int
    source: DataSource
    timestamp: str
    error_message: Optional[str] = None


class PublicDataClient:
    """
    공공데이터포털 API 클라이언트

    실습 1.1의 코드를 확장하여 실제 사용 가능한 클라이언트로 구현
    """

    # 공공데이터포털 기본 URL
    BASE_URL = "https://api.odcloud.kr/api"

    # 주요 공공 API 엔드포인트 예시
    ENDPOINTS = {
        "complaint": "/15084890/v1/uddi:95324d5f-3f42-45f6-a2f7-fb87d8e1d8b2",
        "disaster": "/15084889/v1/uddi:8e3d0e6d-2e8f-42c5-a5f2-8f9c2d0e3b1a",
    }

    def __init__(self, api_key: Optional[str] = None, use_simulator: bool = True):
        """
        Args:
            api_key: 공공데이터포털 API 키 (없으면 시뮬레이터 사용)
            use_simulator: API 키가 없거나 호출 실패 시 시뮬레이터 사용 여부
        """
        self.api_key = api_key
        self.use_simulator = use_simulator
        self.complaint_simulator = PublicDataSimulator(seed=42)
        self.disaster_simulator = DisasterDataSimulator(seed=42)
        self._request_count = 0

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """API 요청 수행"""
        if not self.api_key:
            raise ValueError("API 키가 설정되지 않았습니다.")

        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Infuser {self.api_key}",
            "Content-Type": "application/json",
        }

        if params is None:
            params = {}
        params["serviceKey"] = self.api_key

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        self._request_count += 1

        return response.json()

    def fetch_complaints(self,
                         page: int = 1,
                         per_page: int = 100,
                         region_code: Optional[str] = None) -> APIResponse:
        """
        민원 데이터 조회

        Args:
            page: 페이지 번호
            per_page: 페이지당 레코드 수
            region_code: 지역 코드 필터 (옵션)

        Returns:
            APIResponse: 표준화된 응답
        """
        # 실제 API 호출 시도
        if self.api_key:
            try:
                params = {
                    "page": page,
                    "perPage": per_page,
                }
                if region_code:
                    params["cond[region_code::EQ]"] = region_code

                result = self._make_request(self.ENDPOINTS["complaint"], params)

                return APIResponse(
                    success=True,
                    data=result.get("data", []),
                    total_count=result.get("totalCount", 0),
                    source=DataSource.REAL_API,
                    timestamp=datetime.now().isoformat(),
                )
            except Exception as e:
                if not self.use_simulator:
                    return APIResponse(
                        success=False,
                        data=[],
                        total_count=0,
                        source=DataSource.REAL_API,
                        timestamp=datetime.now().isoformat(),
                        error_message=str(e),
                    )
                # 시뮬레이터로 폴백
                print(f"[경고] API 호출 실패, 시뮬레이터 사용: {e}")

        # 시뮬레이터 사용
        data = self.complaint_simulator.generate_batch(count=per_page)

        if region_code:
            data = [d for d in data if d["region_code"] == region_code]

        return APIResponse(
            success=True,
            data=data,
            total_count=len(data),
            source=DataSource.SIMULATOR,
            timestamp=datetime.now().isoformat(),
        )

    def fetch_disaster_alerts(self, count: int = 10) -> APIResponse:
        """재난 경보 데이터 조회"""
        # 시뮬레이터 사용 (실제 재난 API는 별도 인증 필요)
        data = [self.disaster_simulator.generate_alert() for _ in range(count)]

        return APIResponse(
            success=True,
            data=data,
            total_count=len(data),
            source=DataSource.SIMULATOR,
            timestamp=datetime.now().isoformat(),
        )

    def get_stats(self) -> Dict[str, Any]:
        """클라이언트 통계"""
        return {
            "api_key_configured": self.api_key is not None,
            "simulator_enabled": self.use_simulator,
            "total_requests": self._request_count,
        }


def fetch_public_data(api_url: str, api_key: str, params: Dict = None) -> Dict:
    """
    공공 API 호출 유틸리티 함수 (교재 실습 1.1 확장)

    Args:
        api_url: API 엔드포인트 URL
        api_key: 서비스 키
        params: 추가 파라미터

    Returns:
        API 응답 데이터
    """
    headers = {"Authorization": f"Infuser {api_key}"}

    if params is None:
        params = {}
    params["serviceKey"] = api_key

    response = requests.get(api_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()

    return response.json()


def analyze_response(data: Dict) -> Dict[str, Any]:
    """
    API 응답 분석

    Args:
        data: API 응답 데이터

    Returns:
        분석 결과
    """
    records = data.get("data", [])

    if not records:
        return {"error": "데이터 없음", "total_count": 0}

    # 기본 통계
    analysis = {
        "total_count": data.get("totalCount", len(records)),
        "fetched_count": len(records),
        "first_record": records[0] if records else None,
        "fields": list(records[0].keys()) if records else [],
    }

    return analysis


def demo():
    """데모 실행"""
    print("=" * 60)
    print("공공데이터 API 클라이언트 데모")
    print("=" * 60)

    # 클라이언트 초기화 (API 키 없이 시뮬레이터 사용)
    client = PublicDataClient(api_key=None, use_simulator=True)

    print("\n[1] 클라이언트 상태:")
    stats = client.get_stats()
    print(f"  - API 키 설정: {stats['api_key_configured']}")
    print(f"  - 시뮬레이터 활성화: {stats['simulator_enabled']}")

    print("\n[2] 민원 데이터 조회 (10건):")
    response = client.fetch_complaints(per_page=10)
    print(f"  - 성공 여부: {response.success}")
    print(f"  - 데이터 소스: {response.source.value}")
    print(f"  - 총 건수: {response.total_count}")

    if response.data:
        print(f"\n  첫 번째 레코드:")
        print(json.dumps(response.data[0], indent=4, ensure_ascii=False))

    print("\n[3] 특정 지역 필터 (경기도 - 41):")
    response_filtered = client.fetch_complaints(per_page=20, region_code="41")
    print(f"  - 조회 건수: {response_filtered.total_count}")

    print("\n[4] 재난 경보 데이터 조회:")
    disaster_response = client.fetch_disaster_alerts(count=3)
    for alert in disaster_response.data:
        print(f"  - {alert['alert_id']}: {alert['disaster_type']} (심각도: {alert['severity']})")

    print("\n" + "=" * 60)
    print("데모 완료")


if __name__ == "__main__":
    demo()
