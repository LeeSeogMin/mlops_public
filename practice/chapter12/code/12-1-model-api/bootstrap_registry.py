#!/usr/bin/env python3
"""12장 실습 준비: 모델 레지스트리 재구성(bootstrap).

12장은 서빙을 재발명하지 않는다 — 부하를 거는 대상은 10장에서 배포한 그 API다.
그래서 서빙 앱(app.py)은 10장 파일의 **바이트 동일 복사본**이고(오케스트레이터가
sha256 일치를 확인한다), 이 스크립트는 9·10장과 **같은 데이터·같은 절차**로
chapter12 로컬 레지스트리를 재구성한다. 같은 데이터임은 지문(sha256) 일치로
증명하며, app.py는 별칭(`models:/...@champion`)만 소비한다.

10장 bootstrap과의 유일한 차이: 12장은 컨테이너를 쓰지 않으므로 champion 실물의
model_export(Docker 빌드 컨텍스트) 단계가 없다. 레지스트리(mlflow.db+mlruns)만
재구성하면 호스트 uvicorn이 별칭으로 로드한다.

- v1(baseline_mean): 절대 게이트 통과 + 최초 등록 → champion 승격(상수 예측기, 6.0)
- v2(linear): 게이트 통과했으나 개선 없음 → 승격 반려, challenger 별칭(shadow 대상)

실행: python code/12-1-model-api/bootstrap_registry.py  (또는 run_chapter12.py가 호출)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

API_DIR = Path(__file__).resolve().parent
BASE_DIR = API_DIR.parents[1]  # practice/chapter12
INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"
MLRUNS_DIR = BASE_DIR / "mlruns"

MODEL_NAME = "complaint_daily_forecaster"
MAE_GATE = 1.05
# 9장 실측 지문(ch9_experiment_report.json) — 스냅숏이 갈라지면 여기서 즉시 실패한다
EXPECTED_FP = "96f6b6b3ce9dcdd1da62e0284e0ceea1ec2afec24c522f6df3221ad0ab31f49e"


def build_training_pairs() -> pd.DataFrame:
    """8장 피처 스냅숏 → (전일 건수 → 당일 건수) 쌍 6개. 9·10장과 동일 로직."""
    src = pd.read_parquet(INPUT_DIR / "complaint_daily_features.parquet")
    src = src.assign(day=src["event_timestamp"].dt.normalize() - pd.Timedelta(1, "D"))
    src = src.sort_values(["lawd_cd", "day"])
    pairs = []
    for cd, g in src.groupby("lawd_cd"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            pairs.append({
                "lawd_cd": cd,
                "x_prev_count": int(g.loc[i, "complaint_count"]),
                "y_count": int(g.loc[i + 1, "complaint_count"]),
            })
    return pd.DataFrame(pairs).sort_values(["lawd_cd", "x_prev_count"]).reset_index(drop=True)


def data_fingerprint(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()


def train_and_log(candidate: str, df: pd.DataFrame, fingerprint: str):
    import mlflow
    import mlflow.sklearn
    from sklearn.dummy import DummyRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    X = df[["x_prev_count"]].to_numpy(dtype=float)
    y = df["y_count"].to_numpy(dtype=float)
    if candidate == "baseline_mean":
        model, params = DummyRegressor(strategy="mean"), {"model_type": "DummyRegressor", "strategy": "mean"}
    else:
        model, params = LinearRegression(), {"model_type": "LinearRegression", "fit_intercept": True}

    with mlflow.start_run(run_name=candidate) as run:
        model.fit(X, y)
        mae = float(mean_absolute_error(y, model.predict(X)))
        mlflow.log_params({**params, "n_samples": len(df), "features": "x_prev_count",
                           "data_sha256_16": fingerprint[:16]})
        mlflow.log_metric("train_mae", mae)
        mlflow.set_tags({
            "owner": "민원데이터팀(가상)",
            "purpose": "지역구별 익일 민원 건수 예측(교육용)",
            "data_source": "8장 피처 스냅숏(원천: 시뮬레이션 민원 확정 집계 7/1~7/3)",
            "data_period": "2026-07-01~2026-07-03",
        })
        # 등록 source는 log_model 반환값에서 — 문자열 조립 경로는 로드에서 깨진다(9장 실제 오류)
        model_info = mlflow.sklearn.log_model(model, name="model", input_example=X[:1])
        print(f"[bootstrap] run {candidate}: train_mae={mae:.4f}")
        return run.info.run_id, mae, model_info.model_uri


def main() -> int:
    import os

    # 실행 셸의 환경변수 이름이 모델 메타데이터에 끌려 들어가는 것을 차단한다(기계 노이즈)
    os.environ.setdefault("MLFLOW_RECORD_ENV_VARS_IN_MODEL_LOGGING", "false")

    import mlflow
    from mlflow import MlflowClient

    # 파괴적 정리 전에 의존성 임포트를 끝낸다(9장과 동일한 사고 방지 순서)
    for p in (OUTPUT_DIR / "mlflow.db", MLRUNS_DIR):
        if p.exists():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(f"sqlite:///{OUTPUT_DIR / 'mlflow.db'}")
    # 아티팩트 루트를 명시해 실행 CWD와 무관하게 고정한다(sqlite 백엔드의 기본값은 CWD 기준)
    mlflow.create_experiment("complaint_forecast", artifact_location=str(MLRUNS_DIR))
    mlflow.set_experiment("complaint_forecast")

    df = build_training_pairs()
    fp = data_fingerprint(df)
    print(f"[bootstrap] 훈련 쌍 {len(df)}개, 지문 {fp[:16]}…")
    if fp != EXPECTED_FP:
        raise SystemExit(f"지문 불일치: 9장 스냅숏과 다른 데이터다 — {fp}")

    run_base, mae_base, uri_base = train_and_log("baseline_mean", df, fp)
    run_lin, mae_lin, uri_lin = train_and_log("linear", df, fp)

    client = MlflowClient()
    client.create_registered_model(MODEL_NAME, description="지역구별 익일 민원 건수 예측(교육용·시뮬레이션 데이터)")
    v1 = client.create_model_version(MODEL_NAME, source=uri_base, run_id=run_base,
                                     description="베이스라인(평균) — 9장과 동일 절차 재구성")
    d1 = {"version": int(v1.version), "train_mae": round(mae_base, 4),
          "metric_gate_pass": mae_base <= MAE_GATE, "promoted": False}
    if d1["metric_gate_pass"]:
        client.set_registered_model_alias(MODEL_NAME, "champion", v1.version)
        d1.update(promoted=True, action="champion 별칭 부여(승격)")
    v2 = client.create_model_version(MODEL_NAME, source=uri_lin, run_id=run_lin,
                                     description="선형회귀 후보 — 반려 이력 보존, shadow 평가 대상")
    d2 = {"version": int(v2.version), "train_mae": round(mae_lin, 4),
          "metric_gate_pass": mae_lin <= MAE_GATE, "promoted": False}
    if d2["metric_gate_pass"] and mae_lin < mae_base:
        client.set_registered_model_alias(MODEL_NAME, "champion", v2.version)
        d2.update(promoted=True, action="champion 전환(승격)")
    else:
        client.set_registered_model_alias(MODEL_NAME, "challenger", v2.version)
        d2["action"] = "승격 반려 → challenger 별칭 부여(shadow 평가 대상)"

    # 별칭 존재 여부는 예외가 아니라 aliases 딕셔너리로 확인한다 — 예외를 삼키면 연결·권한
    # 오류까지 "별칭 없음"으로 오인해 재현성을 해친다(challenger는 v2 반려 시에만 존재).
    aliases = client.get_registered_model(MODEL_NAME).aliases  # {alias: version}
    champion_v = int(aliases["champion"])
    challenger_v = int(aliases["challenger"]) if "challenger" in aliases else None
    print(f"[bootstrap] champion=v{champion_v}, challenger=v{challenger_v}")

    # 로드·예측까지가 재구성 검증이다(쓰기 성공 로그를 믿지 않는다 — 9장 교훈)
    loaded = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
    check = float(loaded.predict(pd.DataFrame({"x_prev_count": [9.0]}))[0])

    summary = {
        "data_fingerprint_sha256": fp,
        "fingerprint_matches_ch9": fp == EXPECTED_FP,
        "decisions": [d1, d2],
        "champion_version": champion_v,
        "challenger_version": challenger_v,
        "champion_check_forecast": round(check, 4),
    }
    (OUTPUT_DIR / "ch12_bootstrap_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"[bootstrap] champion 로드 검증 예측={round(check, 4)} (champion=v{champion_v})")
    print("CH12_BOOTSTRAP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
