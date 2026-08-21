#!/usr/bin/env python3
"""본문(docs/chapter17.md) 인용 수치 ↔ 증거 JSON 전수 대조.

증거 JSON(ch17_postmortem_report.json, ch17_error_budget.json)에서 기대값을 읽어,
본문이 인용하는 핵심 수치가 (1) 증거와 일치하고 (2) 본문에 실제로 등장하는지 검사한다.
모두 통과하면 ALL_PASS를 출력한다.

실행: cd practice/chapter17 && venv/bin/python code/verify_numbers.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPORT = BASE / "data" / "output" / "ch17_postmortem_report.json"
BUDGET = BASE / "data" / "output" / "ch17_error_budget.json"
DOCS = BASE.parent.parent / "docs" / "chapter17.md"


def main() -> int:
    if not REPORT.exists():
        print(f"증거 없음: {REPORT} — run_chapter17.py 먼저 실행", file=sys.stderr)
        return 2
    r = json.loads(REPORT.read_text("utf-8"))
    b = json.loads(BUDGET.read_text("utf-8"))
    by_id = {i["id"]: i for i in r["incidents"]}
    cats = r["categories"]
    m12 = by_id["INC-12-single-worker-saturation"]["metrics"]
    m14 = by_id["INC-14-D2-duplicate-resend"]["metrics"]
    m14d3 = by_id["INC-14-D3-api-outage-recovery"]["metrics"]
    m15 = by_id["INC-15-openai-billing-429"]["metrics"]
    budgets = {x["slo_name"]: x for x in b["budgets"]}
    avail = budgets["요청 가용성"]
    pred = budgets["예측 성공"]
    qual = budgets["품질 게이트(MAE)"]

    # (라벨, 증거값, 본문에 반드시 등장해야 하는 문자열) — 증거에서 유도
    checks = [
        ("포스트모템 사건 수", r["incident_count"], "8"),
        ("실제 결함 분류", cats["실제 결함(코드)"], "3"),
        ("주입 드릴 분류", cats["주입 드릴"], "3"),
        ("용량 한계 분류", cats["용량 한계"], "1"),
        ("벤더 장애 분류", cats["벤더 장애"], "1"),
        ("12장 baseline RPS", m12["baseline_rps"], "2498.3"),
        ("12장 spike RPS", m12["spike_rps"], "2788.5"),
        ("12장 CPU peak", m12["cpu_peak_pct"], "106.3"),
        ("12장 워커 1→2 배율", m12["scale_ratio"], "1.26"),
        ("12장 shadow 배율", m12["io_ratio"], "0.68"),
        ("12장 총 요청", m12["total_requests"], "172633"),
        ("12장 부하 실패", m12["total_failures"], "0"),
        ("14장 D2 물리", m14["physical_received"], "28"),
        ("14장 D2 고유", m14["unique"], "17"),
        ("14장 D2 중복", m14["dedup_dropped"], "11"),
        ("14장 D3 마감 보류", m14d3["pending_at_close"], "3"),
        ("14장 D3 복구 후", m14d3["pending_after_recovery"], "0"),
        ("15장 OpenAI 생성", m15["openai_generated"], "0"),
        ("15장 CLOVA 생성", m15["clova_generated"], "8"),
        ("가용성 허용 실패", avail["allowed_failures"], "172"),
        ("가용성 소진", avail["budget_consumed"], "0"),
        ("예측 원 실패", pred["budget_consumed_raw"], "3"),
        ("예측 복구 후 잔여", pred["budget_consumed_after_recovery"], "0"),
        ("품질 채점일", qual["scored_days"], "2"),
        ("품질 초과일", qual["gate_exceeded_days"], "1"),
        ("품질 전체 MAE", qual["overall_mae"], "1.0"),
    ]

    failures = []
    for label, evidence, token in checks:
        if str(evidence) != token and float(evidence) != float(token):
            failures.append(f"[증거불일치] {label}: 증거 {evidence} ≠ 표기 {token}")

    # 핵심 주장은 맥락 고정 문구로 검사(맨숫자 토큰이 다른 곳에 있어도 통과하는 느슨함 방지).
    anchored = [
        "사건 8건",                                  # 포스트모템 총 사건
        f"CLOVA {m15['clova_generated']}",           # 멀티벤더 완주(CLOVA 8)
        f"허용 {avail['allowed_failures']}",          # error budget 허용 실패(172)
        f"물리 {m14['physical_received']}",           # D2 물리 수신(28)
    ]

    if DOCS.exists():
        text = DOCS.read_text("utf-8")
        for label, _evidence, token in checks:
            if token not in text:
                failures.append(f"[본문누락] {label}: '{token}' 본문에 없음")
        for phrase in anchored:
            if phrase not in text:
                failures.append(f"[맥락누락] 고정 문구 '{phrase}' 본문에 없음")
    else:
        print(f"주의: {DOCS} 없음 — 증거 자기정합성만 검사")

    for f in failures:
        print(f)
    total = len(checks)
    print(f"대조 {total}건, 실패 {len(failures)}건")
    print("ALL_PASS" if not failures else "VERIFY_FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
