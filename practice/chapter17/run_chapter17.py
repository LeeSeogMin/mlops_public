#!/usr/bin/env python3
"""17장 실습 17.1 오케스트레이션: 포스트모템·error budget 자동 생성 + PASS 게이트.

  1. 앞 장 실측 증거(data/input)를 읽어 포스트모템·error budget·재발방지·조직안 생성
  2. 증거 JSON(ch17_postmortem_report.json, ch17_error_budget.json) + 마크다운 4종 저장
  3. PASS 게이트: 사건 분류·개수, error budget 소진, 조직 게이트의 불변식을 검증

실행: cd practice/chapter17 && venv/bin/python run_chapter17.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CODE = BASE_DIR / "code" / "17-1-postmortem.py"
INPUT = BASE_DIR / "data" / "input"
OUTPUT = BASE_DIR / "data" / "output"


def _load_module():
    spec = importlib.util.spec_from_file_location("postmortem", CODE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not (INPUT / "incident_catalog.json").exists():
        print(f"입력 없음: {INPUT}", file=sys.stderr)
        return 2

    mod = _load_module()
    report = mod.build_report(INPUT, OUTPUT)

    inc = report["incidents"]
    cats = report["categories"]
    budget = report["error_budget"]["budgets"]
    org = report["org_plan"]

    print(f"=== 17.1 포스트모템: 사건 {report['incident_count']}건 ===")
    for c in ["실제 결함(코드)", "용량 한계", "주입 드릴", "벤더 장애"]:
        print(f"  {c}: {cats.get(c, 0)}건")
    print("=== 17.4 error budget ===")
    for b in budget:
        print(f"  [{b['source_chapter']}장] {b['slo_name']}: {b.get('verdict', b.get('note', ''))[:50]}")
    print(f"=== 17.5 조직 운영안: 역할 {len(org['roles'])}·승인 게이트 {len(org['approval_gates'])} ===")

    # 증거값 인덱스
    by_id = {i["id"]: i for i in inc}
    avail = next(b for b in budget if b["slo_name"] == "요청 가용성")
    pred = next(b for b in budget if b["slo_name"] == "예측 성공")
    qual = next(b for b in budget if b["slo_name"] == "품질 게이트(MAE)")

    # PASS 게이트 — 실습이 시연하려는 불변식을 코드로 검증
    failures = []
    if report["incident_count"] != 8:
        failures.append(f"사건 수 {report['incident_count']}≠8")
    expect_cat = {"실제 결함(코드)": 3, "용량 한계": 1, "주입 드릴": 3, "벤더 장애": 1}
    if cats != expect_cat:
        failures.append(f"사건 분류 {cats}≠{expect_cat}")
    # 12장 용량 한계 사건: 부하 중 failures 0 + 본문이 광고하는 회수 수치 전부 고정
    m12 = by_id["INC-12-single-worker-saturation"]["metrics"]
    if m12["total_failures"] != 0:
        failures.append(f"12장 부하 failures {m12['total_failures']}≠0")
    expect_m12 = {"baseline_rps": 2498.3, "spike_rps": 2788.5, "cpu_peak_pct": 106.3,
                  "scale_ratio": 1.26, "io_ratio": 0.68, "total_requests": 172633}
    for k, v in expect_m12.items():
        if m12[k] != v:
            failures.append(f"12장 {k} {m12[k]}≠{v}")
    # 요청 가용성 예산: 허용 172건 중 소진 0(부하 중 실패 0)
    if avail["budget_consumed"] != 0 or avail["verdict"] != "예산 내":
        failures.append(f"가용성 예산 소진 {avail['budget_consumed']}≠0")
    if avail["allowed_failures"] != 172:
        failures.append(f"가용성 허용 예산 {avail['allowed_failures']}≠172")
    # 예측 성공: 원 실패 3, 복구 후 잔여 0
    if pred["budget_consumed_raw"] != 3 or pred["budget_consumed_after_recovery"] != 0:
        failures.append(f"예측 예산 소진 {pred['budget_consumed_raw']}/복구후 {pred['budget_consumed_after_recovery']}≠3/0")
    # 품질 게이트: 2일 채점 중 1일 초과
    if qual["scored_days"] != 2 or qual["gate_exceeded_days"] != 1:
        failures.append(f"품질 게이트 {qual['scored_days']}일/{qual['gate_exceeded_days']}초과≠2/1")
    # 15장 벤더 장애: OpenAI 생성 0, CLOVA 8
    m15 = by_id["INC-15-openai-billing-429"]["metrics"]
    if (m15["openai_generated"], m15["clova_generated"]) != (0, 8):
        failures.append(f"15장 생성 OpenAI {m15['openai_generated']}/CLOVA {m15['clova_generated']}≠0/8")
    # 14장 D2: 물리 28→고유 17→중복 11
    m14 = by_id["INC-14-D2-duplicate-resend"]["metrics"]
    if (m14["physical_received"], m14["unique"], m14["dedup_dropped"]) != (28, 17, 11):
        failures.append(f"14장 D2 {m14['physical_received']}/{m14['unique']}/{m14['dedup_dropped']}≠28/17/11")
    # 조직 운영안: 역할 4, 승인 게이트 3
    if len(org["roles"]) != 4 or len(org["approval_gates"]) != 3:
        failures.append(f"조직 역할 {len(org['roles'])}/게이트 {len(org['approval_gates'])}≠4/3")
    # 산출물 4종 마크다운 생성 확인
    for fname in ["17-1-postmortem.md", "ch17_recurrence_prevention_plan.md",
                  "ch17_ops_improvement_checklist.md", "ch17_org_operating_plan.md"]:
        if not (OUTPUT / fname).exists():
            failures.append(f"산출물 누락: {fname}")

    print("CH17_RUN_PASS" if not failures else f"CH17_RUN_FAIL({'; '.join(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
