#!/usr/bin/env python3
"""14장 통합 MVP: monitor — 실행 증거에서 통합 리포트와 인수 검수표를 생성한다.

이 파일이 감시 계층의 축소 구현이다(11장 표 11.2의 MVP판): 파이프라인·모델 API가
남긴 증거 파일(집계·품질·예측 스냅샷·운영 카운터)을 읽어,
  1) 통합 리포트(ch14_integration_report.json) — 일별 회계·예측·지연 평가·드릴 실측
  2) 통합 시스템 인수 검수표(ch14_acceptance_checklist.json) — 정본 산출물
를 만든다. 검수표의 각 항목은 사람의 주장이 아니라 실행 증거에서 계산된 불리언이다
(10장 배포 전 체크리스트의 확장 — ML Test Score의 "검수를 검증 가능한 항목으로
명세한다" 접근).

기대값 상수는 앞 장의 커밋된 실측이다(7장 집계·9장 훈련 MAE·9/10장 예측) —
이 값들과의 일치가 곧 "재조립이 원본과 같은 값을 낸다"는 교차 검증이다.

실행: python code/14-1-integrated-mvp/monitor.py  (chapter14 venv, run_chapter14.py가 호출)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MVP_DIR = Path(__file__).resolve().parent
BASE_DIR = MVP_DIR.parents[1]                 # practice/chapter14
OUT_DIR = BASE_DIR / "data" / "output"
MVP_OUT = OUT_DIR / "mvp"
REPO_ROOT = BASE_DIR.parents[1]
CH10_APP = REPO_ROOT / "practice" / "chapter10" / "code" / "10-1-model-api" / "app.py"

DAYS = ["2026-07-01", "2026-07-02", "2026-07-03"]

# ── 앞 장 실측 기대값(커밋된 증거에서 — 새 수치 아님) ──────────────────
# 7장 daily_summary.json 3일치: 지역별 확정 집계
EXPECTED_CH7_REGIONS = {
    "2026-07-01": {"11440": 5, "11620": 5, "11680": 8},
    "2026-07-02": {"11440": 5, "11620": 5, "11680": 6},
    "2026-07-03": {"11440": 6, "11620": 5, "11680": 9},
}
# 7장 quality.json 3일치: 정제 회계(고유 이벤트 기준 — 수송 재전송 제외)
EXPECTED_CH7_QUALITY = {
    "2026-07-01": {"mapped": 18, "missing": 1, "unmapped": 1, "ws_stripped": 1, "alias_fixed": 4},
    "2026-07-02": {"mapped": 16, "missing": 0, "unmapped": 1, "ws_stripped": 1, "alias_fixed": 3},
    "2026-07-03": {"mapped": 20, "missing": 1, "unmapped": 1, "ws_stripped": 1, "alias_fixed": 3},
}
EXPECTED_FORECAST = 6.0        # 9장 champion(평균 예측기)·10장 서빙 실측
EXPECTED_CH9_TRAIN_MAE = 1.0   # 9장 baseline 훈련 MAE — 지연 평가 전체 평균과 일치해야 한다
MAE_GATE = 1.05                # 9장 승격 게이트


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # ── 증거 수집 ──
    days = {}
    for d in DAYS:
        ddir = MVP_OUT / "daily" / d
        days[d] = {
            "closed": (ddir / "_SUCCESS").exists(),
            "summary": read_json(ddir / "daily_summary.json"),
            "quality": read_json(ddir / "quality.json"),
        }
    predictions = read_json(MVP_OUT / "predictions_snapshot.json")
    pending_snapshot = read_json(MVP_OUT / "predictions_snapshot_pending.json") \
        if (MVP_OUT / "predictions_snapshot_pending.json").exists() else []
    counters = read_json(MVP_OUT / "ops_counters.json")
    qfile = MVP_OUT / "quarantine" / "quarantine.jsonl"
    quarantined = [json.loads(l) for l in qfile.read_text(encoding="utf-8").splitlines()] \
        if qfile.exists() else []
    smoke = read_json(OUT_DIR / "ch14_smoke.json")
    boot = read_json(OUT_DIR / "ch14_bootstrap_summary.json")

    # ── 지연 평가(11장): 레이블이 도착한 예측의 일별·전체 MAE ──
    labeled = [p for p in predictions if p["abs_error"] is not None]
    pending = [p for p in predictions if p["status"] == "pending_retry"]
    mae_by_day = {}
    for d in sorted({p["target_date"] for p in labeled}):
        errs = [p["abs_error"] for p in labeled if p["target_date"] == d]
        mae_by_day[d] = round(sum(errs) / len(errs), 4)
    overall_mae = round(sum(p["abs_error"] for p in labeled) / len(labeled), 4) if labeled else None
    unlabeled = [p for p in predictions if p["abs_error"] is None and p["status"] == "ok"]

    # ── 재조립 교차 검증(14.2 표 14.3) ──
    app_match = sha256(MVP_DIR / "model-api" / "app.py") == sha256(CH10_APP)
    agg_match = {d: {r["lawd_cd"]: r["count"] for r in days[d]["summary"]["by_region"]}
                 == EXPECTED_CH7_REGIONS[d] for d in DAYS}
    quality_match = {d: all(days[d]["quality"][k] == v
                            for k, v in EXPECTED_CH7_QUALITY[d].items()) for d in DAYS}
    forecasts_ok = [p for p in predictions if p["status"] == "ok"]
    forecast_match = bool(forecasts_ok) and all(p["forecast"] == EXPECTED_FORECAST
                                                for p in forecasts_ok)

    # ── 드릴 실측 요약(14.5) ──
    d2q = days["2026-07-02"]["quality"]
    drills = {
        "D1_poison_isolation": {
            "quarantined": len(quarantined),
            "reasons": sorted({q["reason"] for q in quarantined}),
            "pipeline_continued": days["2026-07-03"]["closed"],
            "day3_mapped_intact": days["2026-07-03"]["quality"]["mapped"]
            == EXPECTED_CH7_QUALITY["2026-07-03"]["mapped"],
        },
        "D2_duplicate_resend": {
            "physical_received": d2q["physical_received"],
            "unique": d2q["unique"],
            "dedup_dropped": d2q["dedup_dropped"],
            "mapped_unchanged": d2q["mapped"] == EXPECTED_CH7_QUALITY["2026-07-02"]["mapped"],
        },
        "D3_api_outage_recovery": {
            "pending_at_close": len([p for p in pending_snapshot
                                     if p["status"] == "pending_retry"]),
            "pending_errors": sorted({p["error"] for p in pending_snapshot
                                      if p["status"] == "pending_retry"}),
            "day3_closed_despite_outage": days["2026-07-03"]["closed"],
            "pending_after_recovery": len(pending),
            "recovered_attempts": sorted({p["attempts"] for p in predictions
                                          if p["target_date"] == "2026-07-04"}),
        },
    }

    # ── 통합 시스템 인수 검수표(정본 산출물) ──
    checklist = {
        "01_E2E_경로_3일_마감(_SUCCESS_3개)": all(days[d]["closed"] for d in DAYS),
        "02_집계가_7장_확정치와_일치(재구현_검증)": all(agg_match.values()),
        "03_정제_회계가_7장과_일치(4갈래_분리_보고)": all(quality_match.values()),
        "04_회계_보존식_성립(물리=고유+중복,고유=매핑+미기재+미매핑)":
            all(days[d]["quality"]["preservation_ok"] for d in DAYS),
        "05_중복_재전송_무해(물리28→매핑16_불변)":
            d2q["physical_received"] == 28 and drills["D2_duplicate_resend"]["mapped_unchanged"],
        "06_오염_이벤트_격리(격리1건_파이프라인_지속)":
            len(quarantined) == 1 and drills["D1_poison_isolation"]["pipeline_continued"],
        "07_예측이_9·10장_실측과_일치(전_호출_6.0)": forecast_match,
        "08_서빙_신원_기록(champion_v1_local-dir)":
            all(p["model_version"] == "1" and p["model_source"] == "local-dir"
                for p in forecasts_ok),
        "09_잘못된_입력_거절(422)": smoke["invalid_input_status"] == 422,
        "10_부분_실패_격리(중단_중_마감_확정+예측만_대기)":
            drills["D3_api_outage_recovery"]["pending_at_close"] == 3
            and drills["D3_api_outage_recovery"]["day3_closed_despite_outage"],
        "11_복구_수렴(재시도_후_대기_0건)": len(pending) == 0 and len(forecasts_ok) == 9,
        "12_지연_평가_기록(일별_MAE_산출)": bool(mae_by_day) and len(labeled) == 6,
        "13_지연_MAE가_9장_훈련_MAE와_일치(1.0_손검산)": overall_mae == EXPECTED_CH9_TRAIN_MAE,
        "14_재조립_증명_서빙앱_바이트동일(10장_sha256)": app_match,
        "15_재조립_증명_피처_지문일치(9장_96f6b6b3…)": boot["fingerprint_matches_ch9"],
        "16_장애_드릴_3종_리허설_완료(runbook_검증)":
            len(quarantined) == 1 and d2q["dedup_dropped"] == 11
            and drills["D3_api_outage_recovery"]["pending_at_close"] == 3,
    }

    import mlflow
    import pandas
    import sklearn
    report = {
        "versions": {"mlflow": mlflow.__version__, "sklearn": sklearn.__version__,
                     "pandas": pandas.__version__,
                     "kafka_python_pinned": "3.0.7", "images": {
                         "kafka": "confluentinc/cp-kafka:7.5.0",
                         "zookeeper": "confluentinc/cp-zookeeper:7.5.0",
                         "base": "python:3.13-slim"}},
        "reassembly_checks": {
            "app_sha256_matches_ch10": app_match,
            "feature_fingerprint_matches_ch9": boot["fingerprint_matches_ch9"],
            "aggregation_matches_ch7": agg_match,
            "quality_matches_ch7": quality_match,
            "all_forecasts_equal_ch9_champion_6_0": forecast_match,
            "overall_delayed_mae_equals_ch9_train_mae": overall_mae == EXPECTED_CH9_TRAIN_MAE,
        },
        "days": {d: {"quality": days[d]["quality"],
                     "summary": days[d]["summary"]} for d in DAYS},
        "predictions": predictions,
        "delayed_evaluation": {
            "labeled": len(labeled), "mae_by_target_date": mae_by_day,
            "overall_mae": overall_mae, "mae_gate": MAE_GATE,
            "gate_exceeded_days": [d for d, m in mae_by_day.items() if m > MAE_GATE],
            "pending_labels": [p["target_date"] for p in unlabeled],
        },
        "drills": drills,
        "ops_counters": counters,
        "smoke": smoke,
    }
    dump_json(OUT_DIR / "ch14_integration_report.json", report)
    dump_json(OUT_DIR / "ch14_acceptance_checklist.json", checklist)

    print("== 인수 검수표 ==")
    for k, v in checklist.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"== 지연 평가: 일별 MAE {mae_by_day}, 전체 {overall_mae}"
          f" (9장 훈련 MAE {EXPECTED_CH9_TRAIN_MAE}), 미채점 {len(unlabeled)}건 ==")
    ok = all(checklist.values())
    print("CH14_MONITOR_" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
