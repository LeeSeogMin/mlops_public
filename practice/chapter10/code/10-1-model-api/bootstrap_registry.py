#!/usr/bin/env python3
"""10장 실습 준비: 모델 레지스트리 재구성(bootstrap).

운영이라면 9장(등록)과 10장(서빙)이 공용 추적 서버 하나를 바라본다. 실습은 그
서버를 장별 로컬 SQLite로 축소했으므로, 9장과 **같은 데이터·같은 절차**로
chapter10 로컬 레지스트리를 재구성한다 — 같은 데이터임은 지문(sha256) 일치로
증명하고, 서빙(app.py)은 9장 예고 그대로 별칭(`models:/...@champion`)만 소비한다.

- v1(baseline_mean): 절대 게이트 통과 + 최초 등록 → champion 승격 (9장과 동일 판정)
- v2(linear): 게이트 통과했으나 개선 없음 → 승격 반려, challenger 별칭 부여
  (표 9.3a의 Staging 관례 — 10.2의 shadow 배포가 이 별칭을 소비한다)
- champion 실물을 model_export/로 내려받아 Docker 빌드 컨텍스트에 고정한다(10.4).

실행: python code/10-1-model-api/bootstrap_registry.py  (또는 run_chapter10.py가 호출)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

API_DIR = Path(__file__).resolve().parent
BASE_DIR = API_DIR.parents[1]  # practice/chapter10
INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"
MLRUNS_DIR = BASE_DIR / "mlruns"
EXPORT_DIR = API_DIR / "model_export"

MODEL_NAME = "complaint_daily_forecaster"
MAE_GATE = 1.05
# 9장 실측 지문(ch9_experiment_report.json) — 스냅숏이 갈라지면 여기서 즉시 실패한다
EXPECTED_FP = "96f6b6b3ce9dcdd1da62e0284e0ceea1ec2afec24c522f6df3221ad0ab31f49e"


def build_training_pairs() -> pd.DataFrame:
    """8장 피처 스냅숏 → (전일 건수 → 당일 건수) 쌍 6개. 9장과 동일 로직."""
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
    # 내려받은 위치가 곧 모델 루트(MLmodel 포함)인지 검증하고, Dockerfile이 참조하는
    # 고정 경로(model_export/model)로 정규화한다
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

    # 실행 셸의 환경변수 이름이 모델 메타데이터에 끌려 들어가는 것을 차단한다
    # (MLflow 기본 동작 — 값은 기록되지 않지만, 기계마다 다른 노이즈가 export에 남는다)
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
        # 반려 후보를 challenger 별칭으로 유지 — 10.2 shadow 배포가 그림자에서 계속 평가한다
        client.set_registered_model_alias(MODEL_NAME, "challenger", v2.version)
        d2["action"] = "승격 반려 → challenger 별칭 부여(shadow 평가 대상)"

    champion_v = int(client.get_model_version_by_alias(MODEL_NAME, "champion").version)
    challenger_v = int(client.get_model_version_by_alias(MODEL_NAME, "challenger").version)
    print(f"[bootstrap] champion=v{champion_v}, challenger=v{challenger_v}")

    exp = export_champion()
    export_info = {
        "model_name": MODEL_NAME,
        "champion_version": champion_v,
        "exported_from": f"models:/{MODEL_NAME}@champion",
        "note": "빌드 시점의 champion을 이미지에 고정(불변 아티팩트) — 10.4",
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
    (OUTPUT_DIR / "ch10_bootstrap_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"[bootstrap] export 로드 검증 예측={exp['export_check_forecast']} (champion=v{champion_v})")
    print("CH10_BOOTSTRAP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
