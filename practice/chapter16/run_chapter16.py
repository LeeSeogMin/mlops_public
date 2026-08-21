#!/usr/bin/env python3
"""16장 실습 16.1 오케스트레이션: 그룹 편향·설명·모델카드·루브릭 생성 + PASS 게이트.

  1. 9장 산출물 스냅숏을 읽어 champion/challenger 재구성(지문 9장 교차 확인)
  2. 그룹별 회귀 공정성·permutation importance·모델카드·정책루브릭·검토표 생성
  3. 증거 JSON/MD 저장
  4. PASS 게이트: 실습이 시연하려는 불변식(손 검산 가능 값)을 코드로 검증

실행: cd practice/chapter16 && venv/bin/python run_chapter16.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CODE = BASE_DIR / "code" / "16-1-fairness-xai.py"
INPUT = BASE_DIR / "data" / "input"
OUTPUT = BASE_DIR / "data" / "output"


def _load_module():
    spec = importlib.util.spec_from_file_location("fairness_xai", CODE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not (INPUT / "ch9_experiment_report.json").exists():
        print(f"입력 없음: {INPUT} — 9장 산출물 스냅숏 필요", file=sys.stderr)
        return 2

    mod = _load_module()
    report = mod.build(INPUT, OUTPUT)

    fc = report["fairness_champion"]
    expl = report["explanation"]
    card = report["_extras"]["model_card"]
    rubric = report["_extras"]["policy_rubric"]
    check = report["public_ai_checklist"]
    by_region = {g["region"]: g for g in fc["groups"]}

    print("=== 16.2 그룹별 편향 평가(champion) ===")
    for g in fc["groups"]:
        print(f"  {g['region']}: MAE {g['mae']} 편향 {g['bias']:+} "
              f"(실측평균 {g['actual_mean']} → 예측평균 {g['pred_mean']})")
    print(f"  전체 MAE {fc['overall_mae']}, 그룹 MAE 격차 {fc['mae_gap']}, 비율 {fc['mae_ratio']} "
          f"(최악 {fc['worst_group']} / 최선 {fc['best_group']})")
    print("=== 16.3 설명 결과 ===")
    print(f"  champion: permutation importance {expl['champion']['permutation_importance']} (상수→피처 무시)")
    print(f"  challenger: 계수 slope {expl['challenger']['coefficient']['slope']}, "
          f"permutation importance {expl['challenger']['permutation_importance']}")
    print(f"=== 16.3 모델 카드 {card['section_count']}절 / 16.4 루브릭 {rubric['criteria_count']}기준 ===")
    print(f"=== 공공 AI 검토 체크리스트: {check['passed']}/{check['total']} ===")

    # PASS 게이트 — 손 검산 가능한 불변식(9장 교차값 포함)
    failures = []
    if not report["fingerprint"]["matches_ch9"]:
        failures.append("훈련 데이터 지문이 9장과 불일치")
    if report["runs"]["champion_baseline_mean"]["constant_prediction"] != 6.0:
        failures.append("champion 상수 예측 ≠ 6.0")
    if fc["overall_mae"] != 1.0:
        failures.append(f"champion 전체 MAE {fc['overall_mae']} ≠ 1.0(9장 baseline)")
    if report["runs"]["challenger_linear"]["train_mae"] != 1.0455:
        failures.append("challenger MAE ≠ 1.0455(9장 linear)")
    if expl["challenger"]["coefficient"]["slope"] != 0.4091:
        failures.append("challenger slope ≠ 0.4091(9장)")
    expect = {"강남구": 1.5, "마포구": 0.5, "관악구": 1.0}
    for region, mae in expect.items():
        if by_region[region]["mae"] != mae:
            failures.append(f"{region} MAE {by_region[region]['mae']} ≠ {mae}")
    if by_region["강남구"]["bias"] != -1.5:
        failures.append("강남 편향 ≠ -1.5(과소예측)")
    if fc["mae_gap"] != 1.0 or fc["mae_ratio"] != 3.0:
        failures.append(f"그룹 MAE 격차/비율 {fc['mae_gap']}/{fc['mae_ratio']} ≠ 1.0/3.0")
    if expl["champion"]["permutation_importance"] != 0.0:
        failures.append("champion permutation importance ≠ 0.0(상수 모델)")
    if card["section_count"] != 9:
        failures.append(f"모델 카드 절 수 {card['section_count']} ≠ 9")
    if rubric["criteria_count"] != 3:
        failures.append(f"루브릭 기준 수 {rubric['criteria_count']} ≠ 3")
    if not check["all_passed"]:
        failures.append(f"공공 AI 체크리스트 {check['passed']}/{check['total']}")

    print("CH16_RUN_PASS" if not failures else f"CH16_RUN_FAIL({'; '.join(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
