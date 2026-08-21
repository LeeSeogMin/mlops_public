"""
JSON 기반 이벤트 로그 파싱 및 탐색적 분석

실습 2.1: 실시간 API 데이터 파싱
- JSON 데이터 파싱
- 시간대별 패턴 분석
- 기초 통계 계산
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter
import os


class JSONEventParser:
    """JSON 이벤트 로그 파서"""

    def __init__(self):
        self.parse_errors = []

    def parse_single(self, json_str: str) -> Optional[Dict[str, Any]]:
        """단일 JSON 문자열 파싱"""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            self.parse_errors.append({"input": json_str[:100], "error": str(e)})
            return None

    def parse_batch(self, records: List[Dict]) -> pd.DataFrame:
        """배치 레코드를 DataFrame으로 변환"""
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)

        # 시간 필드 파싱
        time_columns = ['event_time', 'timestamp', 'measured_at']
        for col in time_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
                df['_parsed_time'] = df[col]
                break

        return df

    def flatten_nested(self, record: Dict, prefix: str = '') -> Dict:
        """중첩된 JSON 평탄화"""
        items = {}
        for key, value in record.items():
            new_key = f"{prefix}{key}" if prefix else key
            if isinstance(value, dict):
                items.update(self.flatten_nested(value, f"{new_key}_"))
            else:
                items[new_key] = value
        return items


class TemporalAnalyzer:
    """시간 기반 패턴 분석기"""

    def __init__(self, df: pd.DataFrame, time_column: str = '_parsed_time'):
        self.df = df.copy()
        self.time_column = time_column

        if time_column in self.df.columns:
            self.df['hour'] = self.df[time_column].dt.hour
            self.df['day_of_week'] = self.df[time_column].dt.dayofweek
            self.df['date'] = self.df[time_column].dt.date

    def hourly_distribution(self) -> pd.Series:
        """시간대별 분포"""
        if 'hour' not in self.df.columns:
            return pd.Series()
        return self.df.groupby('hour').size()

    def daily_distribution(self) -> pd.Series:
        """일별 분포"""
        if 'date' not in self.df.columns:
            return pd.Series()
        return self.df.groupby('date').size()

    def weekday_distribution(self) -> pd.Series:
        """요일별 분포"""
        if 'day_of_week' not in self.df.columns:
            return pd.Series()
        weekday_names = ['월', '화', '수', '목', '금', '토', '일']
        dist = self.df.groupby('day_of_week').size()
        dist.index = [weekday_names[i] for i in dist.index]
        return dist

    def find_peak_hours(self, top_n: int = 3) -> List[Tuple[int, int]]:
        """피크 시간대 찾기"""
        hourly = self.hourly_distribution()
        if hourly.empty:
            return []
        return list(hourly.nlargest(top_n).items())

    def get_temporal_stats(self) -> Dict[str, Any]:
        """시간 관련 통계"""
        if self.time_column not in self.df.columns:
            return {}

        time_col = self.df[self.time_column]
        return {
            "start_time": time_col.min().isoformat() if not time_col.empty else None,
            "end_time": time_col.max().isoformat() if not time_col.empty else None,
            "duration_hours": (time_col.max() - time_col.min()).total_seconds() / 3600 if len(time_col) > 1 else 0,
            "total_records": len(self.df),
            "peak_hours": self.find_peak_hours(),
        }


class CategoricalAnalyzer:
    """범주형 데이터 분석기"""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_categorical_columns(self) -> List[str]:
        """범주형 컬럼 식별"""
        categorical = []
        for col in self.df.columns:
            if self.df[col].dtype == 'object':
                unique_ratio = self.df[col].nunique() / len(self.df)
                if unique_ratio < 0.5:  # 고유값 비율이 50% 미만
                    categorical.append(col)
        return categorical

    def value_counts(self, column: str, top_n: int = 10) -> pd.Series:
        """값 빈도 계산"""
        if column not in self.df.columns:
            return pd.Series()
        return self.df[column].value_counts().head(top_n)

    def get_distribution_summary(self) -> Dict[str, Dict]:
        """모든 범주형 컬럼의 분포 요약"""
        summary = {}
        for col in self.get_categorical_columns():
            vc = self.value_counts(col)
            summary[col] = {
                "unique_count": self.df[col].nunique(),
                "top_values": vc.head(5).to_dict(),
                "null_count": self.df[col].isnull().sum(),
            }
        return summary


class NumericAnalyzer:
    """수치형 데이터 분석기"""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_numeric_columns(self) -> List[str]:
        """수치형 컬럼 식별"""
        return list(self.df.select_dtypes(include=[np.number]).columns)

    def basic_stats(self, column: str) -> Dict[str, float]:
        """기초 통계량"""
        if column not in self.df.columns:
            return {}

        col = self.df[column].dropna()
        return {
            "count": len(col),
            "mean": round(col.mean(), 2),
            "std": round(col.std(), 2),
            "min": col.min(),
            "25%": col.quantile(0.25),
            "50%": col.quantile(0.50),
            "75%": col.quantile(0.75),
            "max": col.max(),
        }

    def detect_outliers(self, column: str, method: str = 'iqr') -> pd.Series:
        """이상치 탐지"""
        if column not in self.df.columns:
            return pd.Series()

        col = self.df[column].dropna()

        if method == 'iqr':
            q1, q3 = col.quantile(0.25), col.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            return self.df[(col < lower) | (col > upper)][column]
        elif method == 'zscore':
            z_scores = (col - col.mean()) / col.std()
            return self.df[abs(z_scores) > 3][column]

        return pd.Series()

    def get_numeric_summary(self) -> Dict[str, Dict]:
        """모든 수치형 컬럼의 통계 요약"""
        summary = {}
        for col in self.get_numeric_columns():
            stats = self.basic_stats(col)
            outliers = self.detect_outliers(col)
            stats["outlier_count"] = len(outliers)
            summary[col] = stats
        return summary


class EDAReport:
    """탐색적 데이터 분석 보고서 생성"""

    def __init__(self, df: pd.DataFrame, time_column: str = '_parsed_time'):
        self.df = df
        self.temporal = TemporalAnalyzer(df, time_column)
        self.categorical = CategoricalAnalyzer(df)
        self.numeric = NumericAnalyzer(df)

    def generate_summary(self) -> Dict[str, Any]:
        """전체 요약 생성"""
        return {
            "overview": {
                "total_records": len(self.df),
                "total_columns": len(self.df.columns),
                "columns": list(self.df.columns),
                "memory_usage_mb": round(self.df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
            },
            "temporal": self.temporal.get_temporal_stats(),
            "categorical": self.categorical.get_distribution_summary(),
            "numeric": self.numeric.get_numeric_summary(),
        }

    def print_report(self):
        """보고서 출력"""
        summary = self.generate_summary()

        print("=" * 70)
        print("탐색적 데이터 분석 (EDA) 보고서")
        print("=" * 70)

        # 개요
        print("\n[1. 데이터 개요]")
        print("-" * 50)
        overview = summary["overview"]
        print(f"  총 레코드 수: {overview['total_records']:,}")
        print(f"  총 컬럼 수: {overview['total_columns']}")
        print(f"  메모리 사용량: {overview['memory_usage_mb']} MB")

        # 시간 분석
        print("\n[2. 시간 패턴 분석]")
        print("-" * 50)
        temporal = summary["temporal"]
        if temporal:
            print(f"  데이터 기간: {temporal.get('start_time', 'N/A')[:10]} ~ {temporal.get('end_time', 'N/A')[:10]}")
            print(f"  총 기간: {temporal.get('duration_hours', 0):.1f} 시간")
            if temporal.get('peak_hours'):
                print("  피크 시간대:")
                for hour, count in temporal['peak_hours']:
                    print(f"    • {hour}시: {count}건")

        # 범주형 분석
        print("\n[3. 범주형 변수 분석]")
        print("-" * 50)
        for col, stats in summary["categorical"].items():
            print(f"\n  [{col}]")
            print(f"    고유값 수: {stats['unique_count']}")
            print(f"    결측값: {stats['null_count']}")
            print("    상위 값:")
            for val, cnt in list(stats['top_values'].items())[:3]:
                print(f"      • {val}: {cnt}건")

        # 수치형 분석
        print("\n[4. 수치형 변수 분석]")
        print("-" * 50)
        for col, stats in summary["numeric"].items():
            if col.startswith('_'):
                continue
            print(f"\n  [{col}]")
            print(f"    평균: {stats.get('mean', 'N/A')}, 표준편차: {stats.get('std', 'N/A')}")
            print(f"    범위: {stats.get('min', 'N/A')} ~ {stats.get('max', 'N/A')}")
            print(f"    이상치 수: {stats.get('outlier_count', 0)}")


def demo():
    """데모 실행"""
    # 샘플 데이터 생성
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from data_types import PublicDataGenerator, DataCategory

    print("=" * 70)
    print("JSON 파싱 및 EDA 데모")
    print("=" * 70)

    generator = PublicDataGenerator(seed=42)

    # 민원 데이터 생성
    print("\n[민원 데이터 분석]")
    complaints = generator.generate_batch(DataCategory.COMPLAINT, count=500)

    parser = JSONEventParser()
    df = parser.parse_batch(complaints)

    report = EDAReport(df)
    report.print_report()

    # 시간대별 분포 시각화 (텍스트)
    print("\n[5. 시간대별 분포]")
    print("-" * 50)
    hourly = report.temporal.hourly_distribution()
    max_count = hourly.max() if not hourly.empty else 1

    for hour in range(24):
        count = hourly.get(hour, 0)
        bar_len = int(count / max_count * 30)
        bar = "█" * bar_len
        print(f"  {hour:02d}시: {bar} ({count})")


if __name__ == "__main__":
    demo()
