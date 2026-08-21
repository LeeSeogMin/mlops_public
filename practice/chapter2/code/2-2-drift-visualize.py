#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2-2-drift-visualize.py
제2장 실습 2.2 — 분포 변화(드리프트) 비교와 텍스트 시각화

두 개의 실제 에어코리아 스냅샷(기준 baseline vs 현재 current)을 받아
같은 측정 변수(기본 pm10Value)의 분포를 비교한다.
- KS 2표본 검정으로 "두 분포가 같은가"를 통계적으로 본다.
- ASCII 히스토그램과 분위수 표로 분포 변화를 눈으로 확인한다.

기본 입력은 22:00(기준)과 다음 정시(현재) 스냅샷이며, 두 시각의 데이터는
실시간이므로 값은 변하고 구조는 같다. 이것이 시간적 드리프트의 직관이다.

실행:
    cd practice/chapter2
    pip install -r code/requirements.txt
    python3 code/2-2-drift-visualize.py \
        --baseline data/input/airquality_seoul_2200.json \
        --current  data/input/airquality_seoul_current.json \
        --col pm10Value
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "data" / "input"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"


def load_series(path: Path, col: str) -> tuple[np.ndarray, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = payload.get("response", {}).get("body", {})
    items = [r for r in body.get("items", []) if isinstance(r, dict)]
    s = pd.to_numeric(
        pd.Series([r.get(col) for r in items]).replace({"-": np.nan, "": np.nan}),
        errors="coerce",
    ).dropna()
    data_time = str(items[0].get("dataTime")) if items else "unknown"
    return s.to_numpy(dtype=float), data_time


def ks_2samp_with_fallback(baseline: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """SciPy가 있으면 scipy.stats.ks_2samp, 없으면 KS 통계량+점근 p-value를 직접 계산."""
    try:
        from scipy import stats  # type: ignore

        stat, p = stats.ks_2samp(baseline, current)
        return float(stat), float(p)
    except Exception:
        x, y = np.sort(baseline), np.sort(current)
        allv = np.sort(np.concatenate([x, y]))
        cdf_x = np.searchsorted(x, allv, side="right") / x.size
        cdf_y = np.searchsorted(y, allv, side="right") / y.size
        d = float(np.max(np.abs(cdf_x - cdf_y)))
        n = x.size * y.size / (x.size + y.size)
        # 점근 p-value(Kolmogorov)
        lam = (np.sqrt(n) + 0.12 + 0.11 / np.sqrt(n)) * d
        p = 2 * sum((-1) ** (k - 1) * np.exp(-2 * (lam ** 2) * (k ** 2)) for k in range(1, 101))
        return d, float(min(max(p, 0.0), 1.0))


def ascii_histogram(baseline: np.ndarray, current: np.ndarray, bins: int = 8, width: int = 40) -> str:
    lo = float(min(baseline.min(), current.min()))
    hi = float(max(baseline.max(), current.max()))
    edges = np.linspace(lo, hi, bins + 1)
    hb, _ = np.histogram(baseline, bins=edges)
    hc, _ = np.histogram(current, bins=edges)
    peak = max(hb.max(), hc.max(), 1)
    lines = [f"구간[{edges[i]:.0f}-{edges[i+1]:.0f})  "
             f"기준 {'#'*int(hb[i]/peak*width):<{width}} {hb[i]:>2}  "
             f"현재 {'*'*int(hc[i]/peak*width):<{width}} {hc[i]:>2}"
             for i in range(bins)]
    return "\n".join(lines)


def quantile_table(baseline: np.ndarray, current: np.ndarray) -> str:
    qs = [0.0, 0.25, 0.5, 0.75, 1.0]
    rows = ["분위수   기준    현재"]
    for q in qs:
        rows.append(f"{int(q*100):>3}%   {np.quantile(baseline, q):>6.1f}  {np.quantile(current, q):>6.1f}")
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Chapter 2 practice 2.2: distribution drift")
    parser.add_argument("--baseline", default=str(INPUT_DIR / "airquality_seoul_2200.json"))
    parser.add_argument("--current", default=str(INPUT_DIR / "airquality_seoul_current.json"))
    parser.add_argument("--col", default="pm10Value", help="비교할 측정 변수")
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args(argv)

    base, base_time = load_series(Path(args.baseline), args.col)
    curr, curr_time = load_series(Path(args.current), args.col)
    if base.size == 0 or curr.size == 0:
        print("비교할 데이터가 비어 있습니다(결측 제거 후 0건).", file=sys.stderr)
        return 2

    stat, p = ks_2samp_with_fallback(base, curr)
    summary = {
        "column": args.col,
        "baseline_time": base_time,
        "current_time": curr_time,
        "baseline_n": int(base.size),
        "current_n": int(curr.size),
        "baseline_mean": round(float(base.mean()), 3),
        "current_mean": round(float(curr.mean()), 3),
        "ks_statistic": round(stat, 4),
        "p_value": p,
        "alpha": args.alpha,
        "drift_detected": bool(p < args.alpha),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "ch2_drift_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    viz = (
        f"[{args.col}] 기준({base_time}) vs 현재({curr_time})\n\n"
        + ascii_histogram(base, curr) + "\n\n" + quantile_table(base, curr) + "\n"
    )
    (OUTPUT_DIR / "ch2_drift_visual.txt").write_text(viz, encoding="utf-8")

    print(
        f"col={args.col} base({base_time},n={base.size},mean={summary['baseline_mean']}) "
        f"curr({curr_time},n={curr.size},mean={summary['current_mean']}) "
        f"KS={summary['ks_statistic']} p={p:.3g} drift={summary['drift_detected']}"
    )
    print("\n" + viz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
