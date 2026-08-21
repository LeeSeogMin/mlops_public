#!/usr/bin/env python3
"""11장 실습 11.1 오케스트레이션: 기준 vs 현재 분포 비교(드리프트 감시).

시나리오
  1. 비교 A — 2026-06-28 22:00 vs 23:00 (2장 실습 2.2와 같은 쌍):
     KS 실측이 2장 본문 값(0.175 / p 0.5786)과 일치하는지 교차 검증한다.
  2. 비교 B — 2026-06-28 22:00 vs 2026-07-07 22:00 (같은 시각·9일 간격):
     비교창을 시각 정렬한 운영형 비교. KS/PSI/KL → 알림 판정 → 권고.
  3. 드리프트 알림 평가 보고서(ch11_drift_report.json) 생성 —
     휘발성 식별자 없음(재실행 바이트 동일 목표).

실행: cd practice/chapter11 && venv/bin/python run_chapter11.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CODE = BASE_DIR / "code" / "11-1-drift-monitoring.py"
INPUT = BASE_DIR / "data" / "input"
OUTPUT = BASE_DIR / "data" / "output"

BASELINE = INPUT / "airquality_seoul_2200_0628.json"
CURRENT_A = INPUT / "airquality_seoul_2300_0628.json"   # 2장 쌍(1시간 간격)
CURRENT_B = INPUT / "airquality_seoul_2200_0707.json"   # 시각 정렬 9일 간격

# 2장 실습 2.2가 같은 쌍에서 얻은 실측(docs/chapter2.md) — 재현 검증 기준
CH2_EXPECTED = {"ks_statistic": 0.175, "p_value": 0.5786,
                "baseline_mean": 20.025, "current_mean": 20.775}


def run_compare(current: Path, tag: str) -> dict:
    out = OUTPUT / f"ch11_compare_{tag}.json"
    subprocess.run(
        [sys.executable, str(CODE),
         "--baseline", str(BASELINE), "--current", str(current),
         "--json-out", str(out)],
        check=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def main() -> int:
    for p in (BASELINE, CURRENT_A, CURRENT_B):
        if not p.exists():
            print(f"입력 스냅샷 없음: {p}", file=sys.stderr)
            return 2
    OUTPUT.mkdir(parents=True, exist_ok=True)

    print("=== 비교 A: 22:00 vs 23:00 (6/28, 2장 재현 검증) ===")
    a = run_compare(CURRENT_A, "a_1hour")
    matches_ch2 = all(abs(a[k] - v) < 1e-9 for k, v in CH2_EXPECTED.items())
    print(f"2장 실측 재현: {matches_ch2}")

    print("\n=== 비교 B: 6/28 22:00 vs 7/7 22:00 (시각 정렬 9일 간격) ===")
    b = run_compare(CURRENT_B, "b_9days")

    report = {
        "practice": "11.1 기준 vs 현재 분포 비교",
        "column": "pm10Value",
        "alert_rule": {
            "ks": "p < 0.05 (2장과 동일 alpha)",
            "psi": "0.1 주의 / 0.25 경보 (신용평가 업계 관행 — Yurdakul 2018)",
            "combine": "경보=KS유의 AND PSI>=0.25, 주의=둘 중 하나, 정상=둘 다 미달",
        },
        "comparison_a_1hour": a,
        "comparison_a_matches_ch2": matches_ch2,
        "comparison_b_9days_time_aligned": b,
        "notes": [
            "비교창 정렬: 기준·현재 모두 22:00 정시 — 일중 변동 교란을 설계로 제거",
            "n=40 소표본 — KS 검정력 낮음, PSI 구간당 기대 8건으로 출렁임에 민감",
            "알림≠재학습: 권고 조치는 원인 분류를 먼저 요구(11.4)",
        ],
    }
    report_path = OUTPUT / "ch11_drift_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(f"\n보고서 저장: {report_path}")

    # PASS 게이트 — 비교 A(2장 재현)만이 아니라 비교 B와 보고서 경로까지 검증한다.
    failures = []
    if not matches_ch2:
        failures.append("2장 재현 불일치")
    for tag, res, expect_time in (("A", a, "2026-06-28 23:00"), ("B", b, "2026-07-07 22:00")):
        if res.get("current_time") != expect_time:
            failures.append(f"비교 {tag} 스냅샷 dataTime 불일치({res.get('current_time')})")
        if not res.get("psi_equals_kl_sum"):
            failures.append(f"비교 {tag} PSI=KL 항등 실패")
        if res.get("alert_level") not in ("정상", "주의", "경보"):
            failures.append(f"비교 {tag} 알림 등급 이상({res.get('alert_level')})")
        if res.get("bins", {}).get("bins_effective") != res.get("bins", {}).get("bins_requested"):
            failures.append(f"비교 {tag} PSI 구간 축소 — 임계 비교 불성립")
    if not report_path.exists():
        failures.append("보고서 미생성")

    print("CH11_RUN_PASS" if not failures else f"CH11_RUN_FAIL({'; '.join(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
