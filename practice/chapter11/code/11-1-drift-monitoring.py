#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
11-1-drift-monitoring.py
제11장 실습 11.1 — 기준 데이터와 현재 데이터의 분포 비교(드리프트 감시)

두 에어코리아 실측 스냅샷(기준 baseline vs 현재 current)의 같은 변수
(기본 pm10Value) 분포를 세 지표로 비교하고, 알림 판정과 권고 조치를
분리해 기록한다.

지표 3종(11.3·보충):
- KS 2표본 검정  — 비모수 검정. p-value가 "두 분포가 다르다"의 통계적 신호
                   (2장 실습 2.2와 동일 방법 — 재현 검증 대상).
- PSI            — 기준 분포의 분위수 구간에 얹은 거리 지표. 신용평가 업계
                   관행 임계(0.1/0.25)를 차용하되 관행임을 명시(Yurdakul 2018).
- KL divergence  — 비대칭 거리. 같은 구간 확률로 계산하며, 양방향 합이
                   PSI와 일치하는 항등식을 수치로 확인한다(보충).

판정의 분리(11.4): 지표 → 알림 등급 → 권고 조치를 별개 필드로 기록한다.
알림이 곧 재학습이 아니다 — 재학습 여부는 원인 분류와 레이블 확보 뒤의 결정.

실행:
    cd practice/chapter11
    source venv/bin/activate   # (Windows: venv\\Scripts\\activate)
    python code/11-1-drift-monitoring.py \
        --baseline data/input/airquality_seoul_2200_0628.json \
        --current  data/input/airquality_seoul_2200_0707.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "data" / "input"

# 알림 규칙(본문 11.4 표와 동일해야 한다 — 코드가 표의 실체)
ALPHA_DEFAULT = 0.05          # KS 유의수준(2장과 동일)
PSI_WATCH, PSI_ALERT = 0.1, 0.25  # 신용평가 업계 관행 임계(출처: Yurdakul 2018)


def load_series(path: Path, col: str) -> tuple[np.ndarray, str]:
    """스냅샷에서 측정값 배열과 dataTime을 꺼낸다(2장 파싱 규약: '-'와 빈값은 결측)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("response", {}).get("body", {}).get("items", [])
    s = pd.to_numeric(
        pd.Series([r.get(col) for r in items if isinstance(r, dict)])
        .replace({"-": np.nan, "": np.nan}),
        errors="coerce",
    ).dropna()
    data_time = str(items[0].get("dataTime")) if items else "unknown"
    return s.to_numpy(dtype=float), data_time


def binned_proportions(baseline: np.ndarray, current: np.ndarray,
                       bins: int) -> tuple[np.ndarray, np.ndarray, list[str], dict]:
    """기준 분포의 분위수로 구간을 만들고 두 표본의 구간 비율을 돌려준다.

    - 구간 경계는 기준(baseline) 분위수 — "기준이 자(尺)"라는 PSI의 관점.
    - 양 끝은 ±inf로 열어 둔다: 현재 값이 기준의 범위를 벗어나도 버려지지 않고
      끝 구간에 잡힌다(범위 밖 값이야말로 드리프트의 신호).
    - 0빈도 구간의 ln 발산을 막기 위해 구간당 0.5를 더하는 스무딩을 쓴다.
    - 이산값·소표본에서는 분위수가 겹쳐 구간 수가 요청보다 줄 수 있다. 구간 수가
      다르면 PSI끼리 비교할 수 없으므로, 축소를 침묵시키지 않고 결과에 기록하고
      경고를 출력한다(같은 기준·같은 구간 수끼리만 임계 비교가 성립한다).
    """
    edges = np.quantile(baseline, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)  # 이산값 중복 분위수 방어
    effective_bins = len(edges) - 1
    if effective_bins < bins:
        print(f"경고: 분위수 중복으로 구간이 {bins}→{effective_bins}개로 축소됨 — "
              f"다른 실행과 PSI 값을 직접 비교하지 말 것", file=sys.stderr)
    edges[0], edges[-1] = -np.inf, np.inf
    labels = [f"[{lo:.1f}, {hi:.1f})" for lo, hi in zip(edges[:-1], edges[1:])]

    def raw_counts(x: np.ndarray) -> np.ndarray:
        counts, _ = np.histogram(x, bins=edges)
        return counts

    def props(counts: np.ndarray) -> np.ndarray:
        smoothed = counts + 0.5
        return smoothed / smoothed.sum()

    cb, cc = raw_counts(baseline), raw_counts(current)
    counts = {"baseline_counts": [int(v) for v in cb],
              "current_counts": [int(v) for v in cc],
              "bins_requested": int(bins),
              "bins_effective": int(effective_bins)}
    return props(cb), props(cc), labels, counts


def psi_and_kl(p_base: np.ndarray, p_curr: np.ndarray) -> dict:
    """구간 확률로 PSI와 양방향 KL을 계산한다. PSI = KL(b‖c) + KL(c‖b)."""
    kl_bc = float(np.sum(p_base * np.log(p_base / p_curr)))
    kl_cb = float(np.sum(p_curr * np.log(p_curr / p_base)))
    psi = float(np.sum((p_curr - p_base) * np.log(p_curr / p_base)))
    return {
        "psi": round(psi, 4),
        "kl_base_to_curr": round(kl_bc, 4),
        "kl_curr_to_base": round(kl_cb, 4),
        "psi_equals_kl_sum": bool(abs(psi - (kl_bc + kl_cb)) < 1e-12),
    }


def judge_alert(p_value: float, psi: float, alpha: float) -> dict:
    """지표 → 알림 등급. 검정(민감·표본 의존)과 거리(크기)를 함께 요구해 오경보를 억제한다."""
    ks_significant = bool(p_value < alpha)
    if psi >= PSI_ALERT:
        psi_band = "경보"
    elif psi >= PSI_WATCH:
        psi_band = "주의"
    else:
        psi_band = "안정"
    if ks_significant and psi >= PSI_ALERT:
        level = "경보"
    elif ks_significant or psi >= PSI_WATCH:
        level = "주의"
    else:
        level = "정상"
    return {"ks_significant": ks_significant, "psi_band": psi_band, "alert_level": level}


def recommend_action(alert_level: str) -> str:
    """알림 등급 → 권고 조치(11.4 판단표의 실체). 재학습은 여기서 결정되지 않는다."""
    return {
        "정상": "조치 없음 — 기준선 유지, 정기 감시 지속",
        "주의": "모니터링 강화 + 원인 분류 착수(계절/정책/시스템 변경/데이터 결함)",
        "경보": "원인 분류 우선 — 데이터 결함이면 수리, 실제 분포 변화면 재학습 후보 "
               "데이터 확보 후 9장 승격 게이트로(알림≠재학습)",
    }[alert_level]


def compare(baseline_path: Path, current_path: Path, col: str,
            alpha: float, bins: int) -> dict:
    base, base_time = load_series(baseline_path, col)
    curr, curr_time = load_series(current_path, col)
    if base.size == 0 or curr.size == 0:
        raise SystemExit("비교할 데이터가 비어 있습니다(결측 제거 후 0건).")

    ks = stats.ks_2samp(base, curr)
    p_base, p_curr, labels, counts = binned_proportions(base, curr, bins)
    dist = psi_and_kl(p_base, p_curr)
    alert = judge_alert(float(ks.pvalue), dist["psi"], alpha)

    return {
        "column": col,
        "baseline_time": base_time,
        "current_time": curr_time,
        "baseline_n": int(base.size),
        "current_n": int(curr.size),
        "baseline_mean": round(float(base.mean()), 3),
        "current_mean": round(float(curr.mean()), 3),
        "ks_statistic": round(float(ks.statistic), 4),
        "p_value": round(float(ks.pvalue), 4),
        "alpha": alpha,
        "bins": {
            "labels": labels,
            **counts,
            "baseline_props": [round(float(v), 4) for v in p_base],
            "current_props": [round(float(v), 4) for v in p_curr],
        },
        **dist,
        **alert,
        "recommended_action": recommend_action(alert["alert_level"]),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Chapter 11 practice 11.1: drift monitoring")
    parser.add_argument("--baseline", default=str(INPUT_DIR / "airquality_seoul_2200_0628.json"))
    parser.add_argument("--current", default=str(INPUT_DIR / "airquality_seoul_2200_0707.json"))
    parser.add_argument("--col", default="pm10Value")
    parser.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    parser.add_argument("--bins", type=int, default=5, help="PSI/KL 구간 수(기준 분위수)")
    parser.add_argument("--json-out", default=None, help="비교 결과 JSON 저장 경로")
    args = parser.parse_args(argv)

    result = compare(Path(args.baseline), Path(args.current), args.col, args.alpha, args.bins)

    print(f"[기준] {result['baseline_time']} n={result['baseline_n']} "
          f"평균 {result['baseline_mean']}")
    print(f"[현재] {result['current_time']} n={result['current_n']} "
          f"평균 {result['current_mean']}")
    print(f"KS={result['ks_statistic']} p={result['p_value']} (alpha={result['alpha']}) | "
          f"PSI={result['psi']} | KL(b→c)={result['kl_base_to_curr']} "
          f"KL(c→b)={result['kl_curr_to_base']}")
    print(f"알림: KS유의={result['ks_significant']} PSI대역={result['psi_band']} "
          f"→ 등급 {result['alert_level']}")
    print(f"권고: {result['recommended_action']}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                       encoding="utf-8")
        print(f"저장: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
