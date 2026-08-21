#!/usr/bin/env python3
"""14장 통합 MVP 준비: 모델 레지스트리 재구성(bootstrap) — 10장과 동일 절차.

통합 장은 부품을 새로 만들지 않는다. 이 파일은 10장 bootstrap의 경로 적응 재구성이며,
같은 피처 스냅숏(지문 강제 확인)·같은 게이트·같은 별칭 규약으로 chapter14 로컬
레지스트리를 만들고 champion 실물을 model_export/에 내려받아 이미지 빌드에 고정한다.
서빙 앱(app.py)은 10장 파일의 바이트 동일 복사본이다 — run_chapter14.py가 sha256
일치를 확인한다("통합은 재발명이 아니라 재조립"의 증명).

실행: python code/14-1-integrated-mvp/model-api/bootstrap_registry.py
      (chapter14 venv — 또는 run_chapter14.py가 호출)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

API_DIR = Path(__file__).resolve().parent          # .../code/14-1-integrated-mvp/model-api
BASE_DIR = API_DIR.parents[2]                      # practice/chapter14
INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"
MLRUNS_DIR = BASE_DIR / "mlruns"
EXPORT_DIR = API_DIR / "model_export"

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
            "purpose": "지역구별 익일 민원 건수 예측(교육용) — 14장 통합 MVP",
            "data_source": "8장 피처 스냅숏(원천: 시뮬레이션 민원 확정 집계 7/1~7/3)",
            "data_period": "2026-07-01~2026-07-03",
        })
        # 등록 source는 log_model 반환값에서 — 문자열 조립 경로는 로드에서 깨진다(9장 실제 오류)
        model_info = mlflow.sklearn.log_model(model, name="model", input_example=X[:1])
        print(f"[bootstrap] run {candidate}: train_mae={mae:.4f}")
        return run.info.run_id, mae, model_info.model_uri


def export_champion() -> dict:
    """champion 실물을 Docker 빌드 컨텍스트로 내려받아 고정한다(불변 아티팩트)."""
    import mlflow
    import mlflow.artifacts

    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    EXPORT_DIR.mkdir(parents=True)
    dst = mlflow.artifacts.download_artifacts(
        artifact_uri=f"models:/{MODEL_NAME}@champion", dst_path=str(EXPORT_DIR / "model")
    )
    dst = Path(dst)
    mlmodel = next(dst.rglob("MLmodel"))
    model_root = mlmodel.parent
    target = EXPORT_DIR / "model"
    if model_root != target:
        tmp = EXPORT_DIR / "_model_tmp"
        shutil.move(str(model_root), str(tmp))
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(tmp), str(target))
    # 로드 검증까지가 export 검증이다(쓰기 성공 로그를 믿지 않는다 — 9장 교훈)
    loaded = mlflow.pyfunc.load_model(str(target))
    check = float(loaded.predict(pd.DataFrame({"x_prev_count": [9.0]}))[0])
    return {"export_check_forecast": round(check, 4)}


def main() -> int:
    import os

    # 실행 셸의 환경변수 이름이 모델 메타데이터에 끌려 들어가는 것을 차단(10장 gotcha)
    os.environ.setdefault("MLFLOW_RECORD_ENV_VARS_IN_MODEL_LOGGING", "false")

    import mlflow
    from mlflow import MlflowClient

    # 파괴적 정리 전에 의존성 임포트를 끝낸다(9장과 동일한 사고 방지 순서)
    for p in (OUTPUT_DIR / "mlflow.db", MLRUNS_DIR):
        if p.exists():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(f"sqlite:///{OUTPUT_DIR / 'mlflow.db'}")
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
                                     description="베이스라인(평균) — 9·10장과 동일 절차 재구성")
    d1 = {"version": int(v1.version), "train_mae": round(mae_base, 4),
          "metric_gate_pass": mae_base <= MAE_GATE, "promoted": False}
    if d1["metric_gate_pass"]:
        client.set_registered_model_alias(MODEL_NAME, "champion", v1.version)
        d1.update(promoted=True, action="champion 별칭 부여(승격)")
    v2 = client.create_model_version(MODEL_NAME, source=uri_lin, run_id=run_lin,
                                     description="선형회귀 후보 — 반려 이력 보존")
    d2 = {"version": int(v2.version), "train_mae": round(mae_lin, 4),
          "metric_gate_pass": mae_lin <= MAE_GATE, "promoted": False}
    if d2["metric_gate_pass"] and mae_lin < mae_base:
        client.set_registered_model_alias(MODEL_NAME, "champion", v2.version)
        d2.update(promoted=True, action="champion 전환(승격)")
    else:
        client.set_registered_model_alias(MODEL_NAME, "challenger", v2.version)
        d2["action"] = "승격 반려 → challenger 별칭 부여(이력 보존)"

    champion_v = int(client.get_model_version_by_alias(MODEL_NAME, "champion").version)
    challenger_v = int(client.get_model_version_by_alias(MODEL_NAME, "challenger").version)
    print(f"[bootstrap] champion=v{champion_v}, challenger=v{challenger_v}")

    exp = export_champion()
    export_info = {
        "model_name": MODEL_NAME,
        "champion_version": champion_v,
        "exported_from": f"models:/{MODEL_NAME}@champion",
        "note": "빌드 시점의 champion을 이미지에 고정(불변 아티팩트) — 10장 규약",
    }
    (EXPORT_DIR / "export_info.json").write_text(
        json.dumps(export_info, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    summary = {
        "data_fingerprint_sha256": fp,
        "fingerprint_matches_ch9": fp == EXPECTED_FP,
        "decisions": [d1, d2],
        "champion_version": champion_v,
        "challenger_version": challenger_v,
        "export": {**export_info, **exp},
    }
    (OUTPUT_DIR / "ch14_bootstrap_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"[bootstrap] export 로드 검증 예측={exp['export_check_forecast']} (champion=v{champion_v})")
    print("CH14_BOOTSTRAP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
