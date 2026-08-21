#!/usr/bin/env python3
"""13장 실습 13.1 오케스트레이션: 피처 거버넌스 보고서 생성 + PASS 게이트.

  1. 8장 정의 + 7장 일별 집계 스냅숏을 읽어 카탈로그·접근로그·품질·변경관리·감사표 생성
  2. 증거 JSON(ch13_governance_report.json, ch13_audit_checklist.json) 저장
  3. PASS 게이트: 카탈로그·접근 판정·품질·감사 점검의 불변식을 검증

실행: cd practice/chapter13 && venv/bin/python run_chapter13.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CODE = BASE_DIR / "code" / "13-1-feature-catalog.py"
INPUT = BASE_DIR / "data" / "input"
OUTPUT = BASE_DIR / "data" / "output"


def _load_module():
    spec = importlib.util.spec_from_file_location("feature_catalog", CODE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not (INPUT / "ch8_feature_definitions.json").exists():
        print(f"입력 없음: {INPUT}", file=sys.stderr)
        return 2

    mod = _load_module()
    report = mod.build_governance(INPUT, OUTPUT)

    cat = report["catalog"]
    acc = report["access_control"]
    qa = report["quality"]
    chg = report["change_management"]
    audit = report["audit_checklist"]

    print("=== 13.2 피처 카탈로그 ===")
    for c in cat["entries"]:
        print(f"  {c['feature_name']}({c['dtype']}) 소유:{c['owner']} "
              f"개인정보:{c['privacy']} 소비자:{len(c['consumers'])}")
    print(f"=== 13.3 접근 제어: {acc['requests']}건 "
          f"허용 {acc['allow']} / 거부 {acc['deny']} ===")
    for r in acc["log"]:
        print(f"  [{r['decision']}] {r['role']}·{r['feature']}·{r['action']} — {r['reason']}")
    print("=== 13.4 품질 규칙 ===")
    for rule in qa["rules"]:
        print(f"  {rule['rule']}: {'PASS' if rule['passed'] else 'FAIL'} ({rule['detail']})")
    print(f"=== 13.4 변경 관리: {chg['feature']} {chg['from_def']} → {chg['to_def']} ===")
    for d in chg["per_day"]:
        mark = " *변경" if d["changed"] else ""
        print(f"  {d['date']}: v1={d['v1_rate']} v2={d['v2_rate']}{mark}")
    print(f"  영향 소비자: {chg['impacted_consumers']}, 영향 행 {chg['changed_rows']}")
    print(f"=== 감사 점검표: {audit['passed']}/{audit['total']} ===")

    # PASS 게이트 — 실습이 시연하려는 불변식을 코드로 검증
    failures = []
    if cat["features"] != 2:
        failures.append(f"카탈로그 피처 수 {cat['features']}≠2")
    if (acc["allow"], acc["deny"]) != (8, 4):
        failures.append(f"허용/거부 {acc['allow']}/{acc['deny']}≠8/4")
    if not qa["all_passed"]:
        failures.append("품질 규칙 미통과")
    if chg["changed_days"] != 1 or chg["changed_rows"] != 3:
        failures.append(f"변경 영향 {chg['changed_days']}일/{chg['changed_rows']}행≠1/3")
    if not audit["all_passed"]:
        failures.append(f"감사 점검 {audit['passed']}/{audit['total']}")
    if report["inputs"]["feature_rows"] != 9:
        failures.append(f"피처 행 {report['inputs']['feature_rows']}≠9")

    print("CH13_RUN_PASS" if not failures else f"CH13_RUN_FAIL({'; '.join(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
