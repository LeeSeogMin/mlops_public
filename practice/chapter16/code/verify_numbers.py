#!/usr/bin/env python3
"""본문(docs/chapter16.md) 인용 수치 ↔ 증거 JSON 전수 대조.

증거 JSON(ch16_fairness_report.json·ch16_model_card.json·ch16_policy_rubric.json)에서
기대값을 읽어, 본문이 인용하는 핵심 수치가 (1) 증거와 일치하고 (2) 본문에 실제로
등장하는지 검사한다. 모두 통과하면 ALL_PASS를 출력한다.

실행: cd practice/chapter16 && venv/bin/python code/verify_numbers.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "output"
REPORT = OUT / "ch16_fairness_report.json"
CARD = OUT / "ch16_model_card.json"
RUBRIC = OUT / "ch16_policy_rubric.json"
DOCS = BASE.parent.parent / "docs" / "chapter16.md"


def main() -> int:
    if not REPORT.exists():
        print(f"증거 없음: {REPORT} — run_chapter16.py 먼저 실행", file=sys.stderr)
        return 2
    r = json.loads(REPORT.read_text("utf-8"))
    card = json.loads(CARD.read_text("utf-8"))
    rubric = json.loads(RUBRIC.read_text("utf-8"))

    fair = r["fairness_champion"]
    runs = r["runs"]
    expl = r["explanation"]
    check = r["public_ai_checklist"]
    by_region = {g["region"]: g for g in fair["groups"]}
    gn, mp, gw = by_region["강남구"], by_region["마포구"], by_region["관악구"]

    # (라벨, 증거값, 본문에 반드시 등장해야 하는 문자열) — 전부 증거에서 유도
    checks = [
        ("훈련 데이터 지문(9장 교차)", r["fingerprint"]["recomputed_16"][:8], "96f6b6b3"),
        ("champion 전체 MAE", fair["overall_mae"], "1.0"),
        ("champion 상수 예측", runs["champion_baseline_mean"]["constant_prediction"], "6.0"),
        ("challenger MAE", runs["challenger_linear"]["train_mae"], "1.0455"),
        ("challenger slope", runs["challenger_linear"]["coef"]["slope"], "0.4091"),
        ("강남 그룹 MAE", gn["mae"], "1.5"),
        ("강남 편향(과소예측)", gn["bias"], "-1.5"),
        ("강남 실측평균", gn["actual_mean"], "7.5"),
        ("마포 그룹 MAE", mp["mae"], "0.5"),
        ("관악 그룹 MAE", gw["mae"], "1.0"),
        ("그룹 MAE 격차", fair["mae_gap"], "1.0"),
        ("그룹 MAE 비율", fair["mae_ratio"], "3.0"),
        ("champion permutation importance", expl["champion"]["permutation_importance"], "0.0"),
        ("모델 카드 절 수", card["section_count"], "9"),
        ("정책 루브릭 기준 수", rubric["criteria_count"], "3"),
        ("공공 AI 검토 총수", check["total"], "12"),
        ("공공 AI 검토 통과", check["passed"], "12"),
    ]

    failures = []
    # 값 자기정합성: 문자열 표기가 증거값과 같은 수를 가리키는가
    for label, evidence, token in checks:
        try:
            same = str(evidence) == token or float(evidence) == float(token)
        except (TypeError, ValueError):
            same = str(evidence) == token
        if not same:
            failures.append(f"[증거불일치] {label}: 증거 {evidence} ≠ 표기 {token}")

    # 핵심 주장은 맥락 고정 문구로 검사한다(맨숫자 토큰의 우연 일치 방지).
    slope = runs["challenger_linear"]["coef"]["slope"]
    linear_mae = runs["challenger_linear"]["train_mae"]
    anchored = [
        f"MAE {gn['mae']}",                        # 강남 그룹 MAE 1.5
        f"격차 {fair['mae_gap']}",                 # 그룹 MAE 격차 1.0
        f"비율 {fair['mae_ratio']}",               # 그룹 MAE 비율 3.0
        f"{check['passed']}/{check['total']}",     # 공공 AI 검토 12/12
        "96f6b6b3",                                # 9장 지문 교차
        f"slope {slope}",                          # challenger 계수(설명) 0.4091
        f"{linear_mae} > {fair['overall_mae']}",   # 선형이 baseline보다 나쁨(1.0455 > 1.0)
        f"정확히 {expl['champion']['permutation_importance']}",  # champion 중요도 정확히 0.0
    ]

    if DOCS.exists():
        # 본문은 가독성을 위해 유니코드 마이너스(U+2212)를 쓸 수 있다 — 값은 동일하므로
        # ASCII 하이픈-마이너스로 정규화해 대조한다(우회가 아니라 표기 정규화).
        text = DOCS.read_text("utf-8").replace("−", "-")
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
    print(f"대조 {len(checks)}건, 실패 {len(failures)}건")
    print("ALL_PASS" if not failures else "VERIFY_FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
