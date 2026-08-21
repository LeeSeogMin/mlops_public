"""
공공 영역 아키텍처 요구사항

3.3 공공 영역 아키텍처 요구사항
- 보안 (암호화, 접근 제어)
- 감사 (로그, 변경 이력)
- 규제 준수 (개인정보, 보관 기간)

3.4 공공 클라우드 환경 선택
- G-Cloud, 민간 CSP, 하이브리드, 온프레미스
"""

from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum


class SecurityLevel(Enum):
    """보안 수준"""
    PUBLIC = "public"           # 공개
    INTERNAL = "internal"       # 내부
    CONFIDENTIAL = "confidential"  # 대외비
    SECRET = "secret"           # 비밀


class CloudType(Enum):
    """클라우드 유형"""
    G_CLOUD = "g_cloud"         # 정부 클라우드
    PRIVATE_CSP = "private_csp"  # 민간 CSP (공공 전용)
    HYBRID = "hybrid"           # 하이브리드
    ON_PREMISE = "on_premise"   # 온프레미스


@dataclass
class SecurityRequirement:
    """보안 요구사항"""
    category: str
    requirements: List[str]
    implementation: List[str]
    verification: List[str]


@dataclass
class CloudOption:
    """클라우드 옵션"""
    name: str
    cloud_type: CloudType
    description: str
    suitable_for: List[str]
    pros: List[str]
    cons: List[str]


# 보안 요구사항
SECURITY_REQUIREMENTS: Dict[str, SecurityRequirement] = {
    "encryption_in_transit": SecurityRequirement(
        category="전송 중 암호화",
        requirements=[
            "TLS 1.3 이상 사용",
            "강력한 암호화 스위트 설정",
            "인증서 유효성 검증",
            "중간자 공격 방지",
        ],
        implementation=[
            "Kafka: security.protocol=SSL",
            "PostgreSQL: ssl=on",
            "HTTP API: HTTPS 강제",
            "내부 통신: mTLS (상호 TLS)",
        ],
        verification=[
            "SSL/TLS 스캔 도구로 검증",
            "인증서 만료 모니터링",
            "암호화 스위트 감사",
        ],
    ),

    "encryption_at_rest": SecurityRequirement(
        category="저장 시 암호화",
        requirements=[
            "AES-256 암호화",
            "키 관리 시스템 (KMS) 사용",
            "키 순환 정책",
            "백업 데이터 암호화",
        ],
        implementation=[
            "Delta Lake: 투명 암호화",
            "PostgreSQL: pgcrypto 확장",
            "S3/GCS: 서버 측 암호화",
            "디스크: LUKS/BitLocker",
        ],
        verification=[
            "암호화 키 감사",
            "암호화 상태 점검",
            "백업 복원 테스트",
        ],
    ),

    "access_control": SecurityRequirement(
        category="접근 제어",
        requirements=[
            "RBAC (역할 기반 접근 제어)",
            "최소 권한 원칙",
            "다중 인증 (MFA)",
            "세션 관리",
        ],
        implementation=[
            "Kafka: ACL 설정",
            "Airflow: RBAC 활성화",
            "Grafana: LDAP/OAuth 연동",
            "PostgreSQL: GRANT/REVOKE",
        ],
        verification=[
            "권한 감사 로그",
            "주기적 권한 검토",
            "비활성 계정 비활성화",
        ],
    ),

    "network_security": SecurityRequirement(
        category="네트워크 보안",
        requirements=[
            "DMZ 구성",
            "방화벽 규칙",
            "네트워크 세그먼테이션",
            "VPN/전용선",
        ],
        implementation=[
            "외부 API: DMZ 배치",
            "내부 통신: 프라이빗 서브넷",
            "접근 IP 화이트리스트",
            "침입 탐지 시스템 (IDS)",
        ],
        verification=[
            "침투 테스트",
            "네트워크 스캔",
            "방화벽 규칙 감사",
        ],
    ),
}

# 감사 요구사항
AUDIT_REQUIREMENTS: Dict[str, SecurityRequirement] = {
    "access_logging": SecurityRequirement(
        category="접근 로그",
        requirements=[
            "모든 데이터 접근 로그 기록",
            "사용자, 시간, 작업 내용 포함",
            "로그 위변조 방지",
            "최소 3년 보관 (공공기록물법)",
        ],
        implementation=[
            "PostgreSQL: pgaudit 확장",
            "Kafka: 감사 로그 활성화",
            "API Gateway: 요청 로그",
            "중앙 로그 수집 (ELK/Loki)",
        ],
        verification=[
            "로그 무결성 검증",
            "보관 기간 점검",
            "로그 검색 테스트",
        ],
    ),

    "change_tracking": SecurityRequirement(
        category="변경 이력 추적",
        requirements=[
            "CDC (Change Data Capture)",
            "변경 전/후 값 기록",
            "변경 사유 기록",
            "롤백 가능성 확보",
        ],
        implementation=[
            "Delta Lake: 시간 여행 (Time Travel)",
            "PostgreSQL: 트리거 기반 이력 테이블",
            "Kafka: 이벤트 소싱",
            "Git: 코드/설정 버전 관리",
        ],
        verification=[
            "시점 복원 테스트",
            "변경 이력 조회 테스트",
            "감사 요청 시뮬레이션",
        ],
    ),

    "retention_policy": SecurityRequirement(
        category="보관 정책",
        requirements=[
            "데이터 유형별 보관 기간 정의",
            "자동 삭제/아카이빙",
            "삭제 증명서 발급",
            "법적 요구사항 준수",
        ],
        implementation=[
            "Kafka: retention.ms 설정",
            "Delta Lake: VACUUM 명령",
            "S3: 수명 주기 정책",
            "아카이빙: Glacier/Coldline",
        ],
        verification=[
            "보관 기간 점검",
            "삭제 로그 확인",
            "아카이빙 복원 테스트",
        ],
    ),
}

# 규제 준수 요구사항
COMPLIANCE_REQUIREMENTS: Dict[str, SecurityRequirement] = {
    "personal_data": SecurityRequirement(
        category="개인정보 보호",
        requirements=[
            "개인정보 마스킹/익명화",
            "동의 기반 수집",
            "목적 외 사용 금지",
            "개인정보 처리 방침 공개",
        ],
        implementation=[
            "마스킹 UDF 적용",
            "익명화 파이프라인",
            "접근 권한 분리",
            "개인정보 암호화 저장",
        ],
        verification=[
            "개인정보 영향 평가 (PIA)",
            "마스킹 적용 점검",
            "접근 로그 감사",
        ],
    ),

    "data_residency": SecurityRequirement(
        category="데이터 주권",
        requirements=[
            "국내 저장 원칙",
            "국외 이전 시 승인 필요",
            "제3자 제공 기록",
            "데이터 소재지 추적",
        ],
        implementation=[
            "G-Cloud 또는 국내 리전 사용",
            "AWS Seoul, Azure Korea Central",
            "데이터 흐름 문서화",
            "국외 이전 시 암호화",
        ],
        verification=[
            "데이터 소재지 점검",
            "제3자 제공 현황",
            "국외 이전 승인 확인",
        ],
    ),
}

# 클라우드 옵션
CLOUD_OPTIONS: Dict[CloudType, CloudOption] = {
    CloudType.G_CLOUD: CloudOption(
        name="G-Cloud (정부 클라우드)",
        cloud_type=CloudType.G_CLOUD,
        description="국가정보자원관리원(NIA) 운영 정부 전용 클라우드",
        suitable_for=[
            "중앙부처",
            "민감 데이터 (비밀/대외비)",
            "높은 보안 등급 요구 시스템",
        ],
        pros=[
            "최고 수준 보안 인증",
            "정부 망 직접 연결",
            "법적 요구사항 기본 충족",
            "데이터 주권 보장",
        ],
        cons=[
            "리소스 확장 절차 복잡",
            "최신 서비스 도입 지연",
            "비용 예측 어려움",
        ],
    ),

    CloudType.PRIVATE_CSP: CloudOption(
        name="민간 CSP (공공 전용)",
        cloud_type=CloudType.PRIVATE_CSP,
        description="AWS GovCloud, Azure Government, NHN 공공클라우드 등",
        suitable_for=[
            "지자체",
            "공공기관",
            "일반 공공데이터",
        ],
        pros=[
            "최신 클라우드 서비스 활용",
            "탄력적 확장",
            "관리형 서비스 다양",
            "CSAP 인증 획득",
        ],
        cons=[
            "비밀/대외비 데이터 제한",
            "벤더 종속 위험",
            "트래픽 비용 발생",
        ],
    ),

    CloudType.HYBRID: CloudOption(
        name="하이브리드 클라우드",
        cloud_type=CloudType.HYBRID,
        description="온프레미스 + 클라우드 혼합 구성",
        suitable_for=[
            "레거시 시스템 연계 필요",
            "단계적 클라우드 전환",
            "데이터 등급별 분리 저장",
        ],
        pros=[
            "유연한 배치",
            "레거시 연계 용이",
            "데이터 등급별 관리",
            "단계적 전환 가능",
        ],
        cons=[
            "운영 복잡도 증가",
            "네트워크 비용",
            "일관성 관리 어려움",
        ],
    ),

    CloudType.ON_PREMISE: CloudOption(
        name="온프레미스",
        cloud_type=CloudType.ON_PREMISE,
        description="자체 데이터센터 구축/운영",
        suitable_for=[
            "완전한 데이터 통제 필요",
            "외부 연결 불가 시스템",
            "특수 하드웨어 요구",
        ],
        pros=[
            "완전한 통제권",
            "네트워크 비용 없음",
            "규제 준수 용이",
            "물리적 보안",
        ],
        cons=[
            "초기 투자 비용 높음",
            "확장 시간 소요",
            "운영 인력 필요",
            "재해 복구 자체 구축",
        ],
    ),
}


class SecurityChecklistGenerator:
    """보안 체크리스트 생성"""

    @staticmethod
    def generate_security_checklist() -> str:
        """보안 체크리스트"""
        return """
┌─────────────────────────────────────────────────────────────────────────────┐
│                     공공 데이터 파이프라인 보안 체크리스트                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [1. 전송 보안]                                                             │
│  □ TLS 1.3 적용 여부                                                        │
│  □ 인증서 유효성 및 만료일 확인                                             │
│  □ 내부 통신 암호화 (mTLS)                                                  │
│  □ API 엔드포인트 HTTPS 강제                                                │
│                                                                             │
│  [2. 저장 보안]                                                             │
│  □ 데이터베이스 암호화 (AES-256)                                            │
│  □ 키 관리 시스템 (KMS) 설정                                                │
│  □ 백업 데이터 암호화                                                       │
│  □ 키 순환 정책 수립                                                        │
│                                                                             │
│  [3. 접근 제어]                                                             │
│  □ RBAC 설정 및 역할 정의                                                   │
│  □ 최소 권한 원칙 적용                                                      │
│  □ 다중 인증 (MFA) 활성화                                                   │
│  □ 비활성 계정 자동 비활성화                                                │
│                                                                             │
│  [4. 네트워크 보안]                                                         │
│  □ DMZ 구성                                                                 │
│  □ 방화벽 규칙 설정                                                         │
│  □ 네트워크 세그먼테이션                                                    │
│  □ 침입 탐지 시스템 (IDS)                                                   │
│                                                                             │
│  [5. 감사 및 로깅]                                                          │
│  □ 접근 로그 활성화                                                         │
│  □ 로그 중앙 수집                                                           │
│  □ 로그 보관 기간 (3년 이상)                                                │
│  □ 로그 위변조 방지                                                         │
│                                                                             │
│  [6. 개인정보 보호]                                                         │
│  □ 개인정보 마스킹 적용                                                     │
│  □ 접근 권한 분리                                                           │
│  □ 개인정보 처리 방침 게시                                                  │
│  □ 개인정보 영향 평가 (PIA) 수행                                            │
│                                                                             │
│  [7. 재해 복구]                                                             │
│  □ 백업 정책 수립                                                           │
│  □ 복구 시점 목표 (RPO) 정의                                                │
│  □ 복구 시간 목표 (RTO) 정의                                                │
│  □ 재해 복구 훈련 실시                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""

    @staticmethod
    def generate_cloud_selection_guide() -> str:
        """클라우드 선택 가이드"""
        return """
┌─────────────────────────────────────────────────────────────────────────────┐
│                        공공 클라우드 선택 가이드                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [데이터 분류에 따른 클라우드 선택]                                         │
│                                                                             │
│  ┌─────────────┐     ┌─────────────────────────────────────────┐           │
│  │ 데이터 분류  │────▶│               클라우드 옵션              │           │
│  └─────────────┘     └─────────────────────────────────────────┘           │
│                                                                             │
│  비밀/대외비  ─────────▶  G-Cloud 또는 온프레미스                           │
│                           (외부 클라우드 불가)                              │
│                                                                             │
│  일반 공공데이터 ───────▶  민간 CSP (CSAP 인증 필수)                        │
│                           AWS GovCloud, Azure Government 등                │
│                                                                             │
│  혼합 데이터 ───────────▶  하이브리드                                       │
│                           (등급별 분리 저장)                                │
│                                                                             │
│  [CSAP 등급별 허용 데이터]                                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ CSAP 상(High)  │ 중요 정보 시스템, 높은 보안 요구               │   │
│  │ CSAP 중(Medium)│ 일반 업무 시스템, 표준 보안                    │   │
│  │ CSAP 하(Low)   │ 비중요 시스템, 기본 보안                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [선택 전 확인사항]                                                         │
│                                                                             │
│  1. 데이터 분류 등급 확인                                                   │
│  2. CSAP 인증 여부 확인                                                     │
│  3. 데이터 소재지 (국내 리전) 확인                                          │
│  4. SLA 및 장애 대응 체계 확인                                              │
│  5. 비용 구조 (트래픽, 저장, 컴퓨팅) 분석                                   │
│  6. 탈퇴 시 데이터 이관 절차 확인                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""


def print_security_summary():
    """보안 요구사항 요약 출력"""
    print("=" * 80)
    print("공공 영역 보안 요구사항")
    print("=" * 80)

    print("\n[3.3.1 보안 요구사항]")
    print("-" * 60)
    for name, req in SECURITY_REQUIREMENTS.items():
        print(f"\n  [{req.category}]")
        for r in req.requirements[:2]:
            print(f"    • {r}")
        print(f"    구현:")
        for impl in req.implementation[:2]:
            print(f"      - {impl}")

    print("\n\n[3.3.2 감사 요구사항]")
    print("-" * 60)
    for name, req in AUDIT_REQUIREMENTS.items():
        print(f"\n  [{req.category}]")
        for r in req.requirements[:2]:
            print(f"    • {r}")

    print("\n\n[3.3.3 규제 준수]")
    print("-" * 60)
    for name, req in COMPLIANCE_REQUIREMENTS.items():
        print(f"\n  [{req.category}]")
        for r in req.requirements[:2]:
            print(f"    • {r}")


def print_cloud_options():
    """클라우드 옵션 출력"""
    print("\n" + "=" * 80)
    print("공공 클라우드 환경 선택")
    print("=" * 80)

    for cloud_type, option in CLOUD_OPTIONS.items():
        print(f"\n[{option.name}]")
        print("-" * 60)
        print(f"  설명: {option.description}")
        print(f"  적합 상황:")
        for suitable in option.suitable_for:
            print(f"    • {suitable}")
        print(f"  장점:")
        for pro in option.pros[:2]:
            print(f"    ✓ {pro}")
        print(f"  단점:")
        for con in option.cons[:2]:
            print(f"    ✗ {con}")


def demo():
    """보안 및 클라우드 데모"""
    print_security_summary()
    print_cloud_options()

    generator = SecurityChecklistGenerator()
    print(generator.generate_security_checklist())
    print(generator.generate_cloud_selection_guide())


if __name__ == "__main__":
    demo()
