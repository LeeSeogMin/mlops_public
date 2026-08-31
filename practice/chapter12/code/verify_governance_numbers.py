#!/usr/bin/env python3
"""상세 원고(lecture/docs/chapter13.md) 인용 수치 ↔ 증거 JSON 전수 대조.

증거 JSON(ch12_governance_report.json)에서 기대값을 읽어,
본문이 인용하는 핵심 수치가 (1) 증거와 일치하고 (2) 본문에 실제로 등장하는지 검사한다.
모두 통과하면 ALL_PASS를 출력한다.

실행: cd practice/chapter12 && venv/bin/python code/verify_governance_numbers.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPORT = BASE / "data" / "output" / "ch12_governance_report.json"
DOCS = BASE.parent.parent / "lecture" / "docs" / "chapter13.md"


def main() -> int:
    if not REPORT.exists():
        print(f"증거 없음: {REPORT} — run_governance.py 먼저 실행", file=sys.stderr)
        return 2
    r = json.loads(REPORT.read_text("utf-8"))
    acc = r["access_control"]
    qa = r["quality"]
    chg = r["change_management"]
    audit = r["audit_checklist"]
    day72 = next(d for d in chg["per_day"] if d["date"] == "2026-07-02")

    # (라벨, 증거값, 본문에 반드시 등장해야 하는 문자열) — 증거에서 유도
    checks = [
        ("카탈로그 피처 수", r["catalog"]["features"], "2"),
        ("피처 원천 행", r["inputs"]["feature_rows"], "9"),
        ("접근 요청 수", acc["requests"], "12"),
        ("접근 허용", acc["allow"], "8"),
        ("접근 거부", acc["deny"], "4"),
        ("품질 규칙 수", len(qa["rules"]), "3"),
        ("품질 통과 행", qa["rows"], "9"),
        ("변경 영향 일수", chg["changed_days"], "1"),
        ("변경 영향 행", chg["changed_rows"], "3"),
        ("v1 실패율(7/2)", day72["v1_rate"], "0.0588"),
        ("v2 실패율(7/2)", day72["v2_rate"], "0.0556"),
        ("감사 점검 총수", audit["total"], "10"),
        ("감사 점검 통과", audit["passed"], "10"),
    ]

    # 값 자기정합성: 문자열 표기가 증거값과 같은 수를 가리키는가
    failures = []
    for label, evidence, token in checks:
        if str(evidence) != token and float(evidence) != float(token):
            failures.append(f"[증거불일치] {label}: 증거 {evidence} ≠ 표기 {token}")

    # 핵심 주장은 맥락 고정 문구로 검사한다(맨숫자 토큰이 다른 곳에 있어도 통과하는 느슨함 방지).
    anchored = [
        f"허용 {acc['allow']}",                    # 접근 허용 건수
        f"거부 {acc['deny']}",                     # 접근 거부 건수
        f"요청 {acc['requests']}",                 # 접근 요청 총수
        f"{qa['rows']}/{qa['rows']}",              # 품질 전행 통과(9/9)
        str(day72["v1_rate"]),                     # 변경 전 실패율(0.0588)
        str(day72["v2_rate"]),                     # 변경 후 실패율(0.0556)
        f"{audit['total']}항목",                   # 감사 점검 항목 수
    ]

    # 본문 등장 여부(문서가 있을 때만)
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
