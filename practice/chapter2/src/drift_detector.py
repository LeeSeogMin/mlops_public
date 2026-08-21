"""
데이터 드리프트 감지 및 시각화

실습 2.2: 드리프트 시각화
- KS 검정을 통한 분포 변화 감지
- PSI(Population Stability Index) 계산
- 시각화
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import os


class DriftSeverity(Enum):
    """드리프트 심각도"""
    NONE = "none"           # 변화 없음
    LOW = "low"             # 약간의 변화
    MEDIUM = "medium"       # 주의 필요
    HIGH = "high"           # 심각한 변화


@dataclass
class DriftResult:
    """드리프트 감지 결과"""
    feature_name: str
    method: str
    statistic: float
    p_value: Optional[float]
    threshold: float
    is_drifted: bool
    severity: DriftSeverity
    details: Dict[str, Any]


class KSTestDriftDetector:
    """Kolmogorov-Smirnov 검정 기반 드리프트 감지"""

    def __init__(self, significance_level: float = 0.05):
        self.significance_level = significance_level

    def detect(self, baseline: np.ndarray, current: np.ndarray,
               feature_name: str = "feature") -> DriftResult:
        """KS 검정 수행"""
        statistic, p_value = stats.ks_2samp(baseline, current)

        is_drifted = p_value < self.significance_level

        # 심각도 결정
        if p_value >= 0.1:
            severity = DriftSeverity.NONE
        elif p_value >= 0.05:
            severity = DriftSeverity.LOW
        elif p_value >= 0.01:
            severity = DriftSeverity.MEDIUM
        else:
            severity = DriftSeverity.HIGH

        return DriftResult(
            feature_name=feature_name,
            method="ks_test",
            statistic=round(statistic, 4),
            p_value=round(p_value, 6),
            threshold=self.significance_level,
            is_drifted=is_drifted,
            severity=severity,
            details={
                "baseline_mean": round(np.mean(baseline), 4),
                "baseline_std": round(np.std(baseline), 4),
                "current_mean": round(np.mean(current), 4),
                "current_std": round(np.std(current), 4),
                "baseline_size": len(baseline),
                "current_size": len(current),
            }
        )


class PSIDriftDetector:
    """Population Stability Index 기반 드리프트 감지"""

    # PSI 해석 기준
    PSI_THRESHOLDS = {
        "none": 0.1,      # PSI < 0.1: 변화 없음
        "low": 0.2,       # 0.1 <= PSI < 0.2: 약간의 변화
        "high": float('inf')  # PSI >= 0.2: 유의미한 변화
    }

    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins

    def calculate_psi(self, baseline: np.ndarray, current: np.ndarray) -> float:
        """PSI 계산"""
        # 동일한 bin 경계 사용
        min_val = min(baseline.min(), current.min())
        max_val = max(baseline.max(), current.max())

        # 범위가 같은 경우 처리
        if min_val == max_val:
            return 0.0

        bin_edges = np.linspace(min_val, max_val, self.n_bins + 1)

        # 각 bin의 비율 계산
        baseline_counts, _ = np.histogram(baseline, bins=bin_edges)
        current_counts, _ = np.histogram(current, bins=bin_edges)

        baseline_pct = baseline_counts / len(baseline)
        current_pct = current_counts / len(current)

        # 0 방지 (Laplace smoothing)
        baseline_pct = np.where(baseline_pct == 0, 0.0001, baseline_pct)
        current_pct = np.where(current_pct == 0, 0.0001, current_pct)

        # PSI 계산
        psi = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))

        return psi

    def detect(self, baseline: np.ndarray, current: np.ndarray,
               feature_name: str = "feature") -> DriftResult:
        """PSI 기반 드리프트 감지"""
        psi = self.calculate_psi(baseline, current)

        # 심각도 결정
        if psi < self.PSI_THRESHOLDS["none"]:
            severity = DriftSeverity.NONE
            is_drifted = False
        elif psi < self.PSI_THRESHOLDS["low"]:
            severity = DriftSeverity.LOW
            is_drifted = False
        else:
            severity = DriftSeverity.HIGH
            is_drifted = True

        return DriftResult(
            feature_name=feature_name,
            method="psi",
            statistic=round(psi, 4),
            p_value=None,
            threshold=self.PSI_THRESHOLDS["low"],
            is_drifted=is_drifted,
            severity=severity,
            details={
                "psi_interpretation": self._interpret_psi(psi),
                "baseline_mean": round(np.mean(baseline), 4),
                "current_mean": round(np.mean(current), 4),
                "n_bins": self.n_bins,
            }
        )

    def _interpret_psi(self, psi: float) -> str:
        """PSI 해석"""
        if psi < 0.1:
            return "분포 안정 (변화 없음)"
        elif psi < 0.2:
            return "약간의 변화 (모니터링 권장)"
        else:
            return "유의미한 변화 (조치 필요)"


class ComprehensiveDriftDetector:
    """KS 검정과 PSI를 결합한 종합 드리프트 감지"""

    def __init__(self, ks_threshold: float = 0.05, psi_threshold: float = 0.2):
        self.ks_detector = KSTestDriftDetector(significance_level=ks_threshold)
        self.psi_detector = PSIDriftDetector()
        self.psi_threshold = psi_threshold

    def detect_all_features(self, baseline_df: pd.DataFrame,
                            current_df: pd.DataFrame,
                            numeric_columns: List[str] = None) -> Dict[str, Any]:
        """모든 수치형 피처에 대해 드리프트 감지"""
        if numeric_columns is None:
            numeric_columns = list(baseline_df.select_dtypes(include=[np.number]).columns)

        results = {
            "features": {},
            "summary": {
                "total_features": len(numeric_columns),
                "drifted_features": 0,
                "drift_ratio": 0.0,
            }
        }

        drifted_count = 0

        for col in numeric_columns:
            if col.startswith('_'):
                continue

            baseline = baseline_df[col].dropna().values
            current = current_df[col].dropna().values

            if len(baseline) == 0 or len(current) == 0:
                continue

            ks_result = self.ks_detector.detect(baseline, current, col)
            psi_result = self.psi_detector.detect(baseline, current, col)

            # 두 방법 모두에서 드리프트로 판정 시 확정
            confirmed_drift = ks_result.is_drifted and psi_result.is_drifted

            if confirmed_drift:
                drifted_count += 1

            results["features"][col] = {
                "ks_test": {
                    "statistic": ks_result.statistic,
                    "p_value": ks_result.p_value,
                    "is_drifted": ks_result.is_drifted,
                    "severity": ks_result.severity.value,
                },
                "psi": {
                    "value": psi_result.statistic,
                    "is_drifted": psi_result.is_drifted,
                    "interpretation": psi_result.details.get("psi_interpretation"),
                },
                "confirmed_drift": confirmed_drift,
                "baseline_stats": {
                    "mean": ks_result.details["baseline_mean"],
                    "std": ks_result.details["baseline_std"],
                },
                "current_stats": {
                    "mean": ks_result.details["current_mean"],
                    "std": ks_result.details["current_std"],
                },
            }

        results["summary"]["drifted_features"] = drifted_count
        results["summary"]["drift_ratio"] = drifted_count / len(numeric_columns) if numeric_columns else 0

        return results


class DriftVisualizer:
    """드리프트 시각화 (텍스트 기반)"""

    @staticmethod
    def print_distribution_comparison(baseline: np.ndarray, current: np.ndarray,
                                       feature_name: str, bins: int = 10):
        """분포 비교 텍스트 시각화"""
        print(f"\n[{feature_name}] 분포 비교")
        print("-" * 50)

        min_val = min(baseline.min(), current.min())
        max_val = max(baseline.max(), current.max())
        bin_edges = np.linspace(min_val, max_val, bins + 1)

        baseline_hist, _ = np.histogram(baseline, bins=bin_edges)
        current_hist, _ = np.histogram(current, bins=bin_edges)

        max_count = max(baseline_hist.max(), current_hist.max())

        print(f"  범위: {min_val:.2f} ~ {max_val:.2f}")
        print()
        print("  Baseline vs Current")

        for i in range(bins):
            bin_start = bin_edges[i]
            bin_end = bin_edges[i + 1]
            b_count = baseline_hist[i]
            c_count = current_hist[i]

            b_bar_len = int(b_count / max_count * 15) if max_count > 0 else 0
            c_bar_len = int(c_count / max_count * 15) if max_count > 0 else 0

            b_bar = "█" * b_bar_len
            c_bar = "▓" * c_bar_len

            print(f"  {bin_start:6.1f}-{bin_end:6.1f}: {b_bar:<15} | {c_bar:<15}")

        print()
        print("  █ = Baseline, ▓ = Current")

    @staticmethod
    def print_drift_report(results: Dict[str, Any]):
        """드리프트 분석 보고서 출력"""
        print("=" * 70)
        print("데이터 드리프트 분석 보고서")
        print("=" * 70)

        summary = results["summary"]
        print(f"\n[요약]")
        print(f"  분석 피처 수: {summary['total_features']}")
        print(f"  드리프트 감지: {summary['drifted_features']}개")
        print(f"  드리프트 비율: {summary['drift_ratio']:.1%}")

        print(f"\n[피처별 상세]")
        print("-" * 70)

        for feature, data in results["features"].items():
            drift_status = "⚠️ 드리프트" if data["confirmed_drift"] else "✅ 안정"
            print(f"\n  [{feature}] {drift_status}")

            ks = data["ks_test"]
            psi = data["psi"]

            print(f"    KS 검정: statistic={ks['statistic']:.4f}, p-value={ks['p_value']:.4f}")
            print(f"    PSI: {psi['value']:.4f} ({psi['interpretation']})")

            baseline = data["baseline_stats"]
            current = data["current_stats"]
            print(f"    Baseline: mean={baseline['mean']:.2f}, std={baseline['std']:.2f}")
            print(f"    Current:  mean={current['mean']:.2f}, std={current['std']:.2f}")


def create_drift_scenario():
    """드리프트 시나리오 생성 (교재 2.3 데이터 드리프트 예시)"""
    np.random.seed(42)

    scenarios = {
        "정상 (변화 없음)": {
            "baseline": np.random.normal(100, 15, 500),
            "current": np.random.normal(100, 15, 500),
        },
        "정책 변화 (평균 이동)": {
            "baseline": np.random.normal(100, 15, 500),
            "current": np.random.normal(120, 15, 500),  # 평균 20 증가
        },
        "계절성 (분산 증가)": {
            "baseline": np.random.normal(100, 15, 500),
            "current": np.random.normal(100, 30, 500),  # 분산 2배
        },
        "외부 이벤트 (분포 변화)": {
            "baseline": np.random.normal(100, 15, 500),
            "current": np.concatenate([
                np.random.normal(80, 10, 300),   # 기존 분포
                np.random.normal(150, 20, 200),  # 새로운 분포 추가
            ]),
        },
    }

    return scenarios


def demo():
    """데모 실행"""
    print("=" * 70)
    print("데이터 드리프트 감지 데모")
    print("=" * 70)

    print("\n공공 데이터에서 드리프트가 발생하는 원인:")
    print("-" * 50)
    causes = [
        "1. 정책 변화: 새 민원 유형 신설, 처리 기준 변경",
        "2. 계절성: 동절기 난방 민원 증가, 하절기 에어컨 민원",
        "3. 외부 이벤트: 재난 발생 시 관련 민원 급증",
        "4. 시스템 변경: API 스키마 변경, 데이터 수집 방식 변경",
    ]
    for cause in causes:
        print(f"  {cause}")

    # 드리프트 시나리오 생성
    scenarios = create_drift_scenario()

    detector = ComprehensiveDriftDetector()
    visualizer = DriftVisualizer()

    print("\n" + "=" * 70)
    print("드리프트 시나리오별 분석")
    print("=" * 70)

    for scenario_name, data in scenarios.items():
        print(f"\n\n{'#' * 60}")
        print(f"시나리오: {scenario_name}")
        print('#' * 60)

        baseline = data["baseline"]
        current = data["current"]

        # KS 검정
        ks_detector = KSTestDriftDetector()
        ks_result = ks_detector.detect(baseline, current, "metric")

        # PSI
        psi_detector = PSIDriftDetector()
        psi_result = psi_detector.detect(baseline, current, "metric")

        print(f"\n[KS 검정 결과]")
        print(f"  Statistic: {ks_result.statistic}")
        print(f"  P-value: {ks_result.p_value}")
        print(f"  드리프트 여부: {'예' if ks_result.is_drifted else '아니오'}")
        print(f"  심각도: {ks_result.severity.value}")

        print(f"\n[PSI 결과]")
        print(f"  PSI 값: {psi_result.statistic}")
        print(f"  해석: {psi_result.details['psi_interpretation']}")

        # 분포 비교 시각화
        visualizer.print_distribution_comparison(baseline, current, "metric")


if __name__ == "__main__":
    demo()
