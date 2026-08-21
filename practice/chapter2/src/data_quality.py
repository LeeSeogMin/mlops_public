"""
데이터 품질 검증

2.2 데이터 품질 이슈
- 중복 감지
- 지연 데이터 처리
- 스키마 불일치 감지
- 결측치 분석
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib


class QualityIssueType(Enum):
    """품질 이슈 유형"""
    DUPLICATE = "duplicate"          # 중복
    LATE_ARRIVAL = "late_arrival"    # 지연 도착
    SCHEMA_MISMATCH = "schema_mismatch"  # 스키마 불일치
    MISSING_VALUE = "missing_value"  # 결측치
    OUTLIER = "outlier"              # 이상치
    INVALID_FORMAT = "invalid_format"  # 형식 오류


@dataclass
class QualityIssue:
    """품질 이슈 레코드"""
    issue_type: QualityIssueType
    severity: str  # low, medium, high
    affected_records: int
    percentage: float
    description: str
    sample_records: List[Any]


class DuplicateDetector:
    """중복 데이터 감지"""

    def __init__(self, key_columns: List[str] = None):
        self.key_columns = key_columns

    def _generate_hash(self, record: Dict) -> str:
        """레코드 해시 생성"""
        if self.key_columns:
            key_values = {k: record.get(k) for k in self.key_columns}
        else:
            key_values = record

        hash_input = str(sorted(key_values.items())).encode()
        return hashlib.sha256(hash_input).hexdigest()[:16]

    def detect(self, df: pd.DataFrame) -> QualityIssue:
        """중복 감지"""
        if self.key_columns:
            duplicates = df[df.duplicated(subset=self.key_columns, keep=False)]
        else:
            duplicates = df[df.duplicated(keep=False)]

        dup_count = len(duplicates)
        total = len(df)
        percentage = (dup_count / total * 100) if total > 0 else 0

        # 심각도 결정
        if percentage < 1:
            severity = "low"
        elif percentage < 5:
            severity = "medium"
        else:
            severity = "high"

        return QualityIssue(
            issue_type=QualityIssueType.DUPLICATE,
            severity=severity,
            affected_records=dup_count,
            percentage=round(percentage, 2),
            description=f"중복 레코드 {dup_count}건 감지 ({percentage:.2f}%)",
            sample_records=duplicates.head(3).to_dict('records') if dup_count > 0 else [],
        )


class LateArrivalDetector:
    """지연 데이터 감지"""

    def __init__(self, time_column: str, threshold_minutes: int = 10):
        self.time_column = time_column
        self.threshold = timedelta(minutes=threshold_minutes)

    def detect(self, df: pd.DataFrame, reference_time: datetime = None) -> QualityIssue:
        """지연 도착 데이터 감지"""
        if reference_time is None:
            reference_time = datetime.now()

        if self.time_column not in df.columns:
            return QualityIssue(
                issue_type=QualityIssueType.LATE_ARRIVAL,
                severity="low",
                affected_records=0,
                percentage=0,
                description=f"시간 컬럼 '{self.time_column}' 없음",
                sample_records=[],
            )

        time_col = pd.to_datetime(df[self.time_column])

        # 타임존 정규화 (tz-naive로 통일)
        if time_col.dt.tz is not None:
            time_col = time_col.dt.tz_localize(None)

        # 지연 계산 (실제로는 ingestion_time과 비교해야 하지만 시뮬레이션)
        # 여기서는 데이터가 얼마나 오래된지 확인
        delays = reference_time - time_col
        late_arrivals = df[delays > self.threshold]

        late_count = len(late_arrivals)
        total = len(df)
        percentage = (late_count / total * 100) if total > 0 else 0

        if percentage < 5:
            severity = "low"
        elif percentage < 20:
            severity = "medium"
        else:
            severity = "high"

        return QualityIssue(
            issue_type=QualityIssueType.LATE_ARRIVAL,
            severity=severity,
            affected_records=late_count,
            percentage=round(percentage, 2),
            description=f"{self.threshold.seconds // 60}분 이상 지연된 데이터 {late_count}건",
            sample_records=[],
        )


class SchemaMismatchDetector:
    """스키마 불일치 감지"""

    def __init__(self, expected_schema: Dict[str, type]):
        self.expected_schema = expected_schema

    def detect(self, df: pd.DataFrame) -> QualityIssue:
        """스키마 불일치 감지"""
        issues = []

        # 누락된 컬럼
        missing_columns = set(self.expected_schema.keys()) - set(df.columns)
        if missing_columns:
            issues.append(f"누락된 컬럼: {missing_columns}")

        # 추가된 컬럼
        extra_columns = set(df.columns) - set(self.expected_schema.keys())
        if extra_columns:
            issues.append(f"예상 외 컬럼: {extra_columns}")

        # 타입 불일치 (간단한 체크)
        for col, expected_type in self.expected_schema.items():
            if col in df.columns:
                actual_type = df[col].dtype
                if expected_type == str and actual_type != 'object':
                    issues.append(f"'{col}': 예상 str, 실제 {actual_type}")
                elif expected_type in [int, float] and not np.issubdtype(actual_type, np.number):
                    issues.append(f"'{col}': 예상 숫자, 실제 {actual_type}")

        issue_count = len(issues)
        severity = "high" if issue_count > 2 else "medium" if issue_count > 0 else "low"

        return QualityIssue(
            issue_type=QualityIssueType.SCHEMA_MISMATCH,
            severity=severity,
            affected_records=issue_count,
            percentage=0,
            description="; ".join(issues) if issues else "스키마 일치",
            sample_records=[],
        )


class MissingValueAnalyzer:
    """결측치 분석"""

    def analyze(self, df: pd.DataFrame) -> QualityIssue:
        """결측치 분석"""
        missing_stats = df.isnull().sum()
        total_missing = missing_stats.sum()
        total_cells = df.size

        percentage = (total_missing / total_cells * 100) if total_cells > 0 else 0

        # 컬럼별 결측률
        column_missing = {}
        for col in df.columns:
            col_missing_pct = df[col].isnull().sum() / len(df) * 100
            if col_missing_pct > 0:
                column_missing[col] = round(col_missing_pct, 2)

        if percentage < 1:
            severity = "low"
        elif percentage < 5:
            severity = "medium"
        else:
            severity = "high"

        return QualityIssue(
            issue_type=QualityIssueType.MISSING_VALUE,
            severity=severity,
            affected_records=int(total_missing),
            percentage=round(percentage, 2),
            description=f"총 결측값 {total_missing}개, 컬럼별: {column_missing}",
            sample_records=[],
        )


class DataQualityReport:
    """데이터 품질 종합 보고서"""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.issues: List[QualityIssue] = []

    def run_all_checks(self,
                       key_columns: List[str] = None,
                       time_column: str = None,
                       expected_schema: Dict[str, type] = None) -> Dict[str, Any]:
        """모든 품질 검사 실행"""

        # 중복 검사
        dup_detector = DuplicateDetector(key_columns)
        self.issues.append(dup_detector.detect(self.df))

        # 지연 검사
        if time_column:
            late_detector = LateArrivalDetector(time_column)
            self.issues.append(late_detector.detect(self.df))

        # 스키마 검사
        if expected_schema:
            schema_detector = SchemaMismatchDetector(expected_schema)
            self.issues.append(schema_detector.detect(self.df))

        # 결측치 분석
        missing_analyzer = MissingValueAnalyzer()
        self.issues.append(missing_analyzer.analyze(self.df))

        return self.generate_report()

    def generate_report(self) -> Dict[str, Any]:
        """보고서 생성"""
        high_severity = sum(1 for i in self.issues if i.severity == "high")
        medium_severity = sum(1 for i in self.issues if i.severity == "medium")

        return {
            "summary": {
                "total_records": len(self.df),
                "total_issues": len(self.issues),
                "high_severity_count": high_severity,
                "medium_severity_count": medium_severity,
                "overall_quality": self._calculate_quality_score(),
            },
            "issues": [
                {
                    "type": issue.issue_type.value,
                    "severity": issue.severity,
                    "affected_records": issue.affected_records,
                    "percentage": issue.percentage,
                    "description": issue.description,
                }
                for issue in self.issues
            ],
        }

    def _calculate_quality_score(self) -> str:
        """품질 점수 계산"""
        high_count = sum(1 for i in self.issues if i.severity == "high")
        medium_count = sum(1 for i in self.issues if i.severity == "medium")

        if high_count > 0:
            return "Poor"
        elif medium_count > 1:
            return "Fair"
        elif medium_count == 1:
            return "Good"
        else:
            return "Excellent"

    def print_report(self):
        """보고서 출력"""
        report = self.generate_report()

        print("=" * 70)
        print("데이터 품질 보고서")
        print("=" * 70)

        summary = report["summary"]
        print(f"\n[요약]")
        print(f"  총 레코드 수: {summary['total_records']:,}")
        print(f"  발견된 이슈: {summary['total_issues']}개")
        print(f"    - 높음(High): {summary['high_severity_count']}개")
        print(f"    - 중간(Medium): {summary['medium_severity_count']}개")
        print(f"  전체 품질 등급: {summary['overall_quality']}")

        print(f"\n[상세 이슈]")
        print("-" * 70)

        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}

        for issue in report["issues"]:
            icon = severity_icon.get(issue["severity"], "⚪")
            print(f"\n  {icon} [{issue['type'].upper()}] {issue['severity'].upper()}")
            print(f"     {issue['description']}")
            if issue["affected_records"] > 0:
                print(f"     영향 레코드: {issue['affected_records']}개 ({issue['percentage']}%)")


def demo():
    """데모 실행"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from data_types import PublicDataGenerator, DataCategory

    print("=" * 70)
    print("데이터 품질 검증 데모")
    print("=" * 70)

    generator = PublicDataGenerator(seed=42)

    # 샘플 데이터 생성 (일부러 품질 이슈 포함)
    complaints = generator.generate_batch(DataCategory.COMPLAINT, count=200)

    # 중복 추가
    complaints.extend(complaints[:10])

    # 결측치 추가
    for i in range(5):
        complaints[i]["region_code"] = None

    df = pd.DataFrame(complaints)

    # 품질 검사 실행
    report = DataQualityReport(df)
    report.run_all_checks(
        key_columns=["event_time", "citizen_id"],
        time_column="event_time",
        expected_schema={
            "event_time": str,
            "citizen_id": str,
            "issue_type": str,
            "region_code": str,
            "content_length": int,
        }
    )

    report.print_report()


if __name__ == "__main__":
    demo()
