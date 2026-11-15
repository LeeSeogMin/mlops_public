"""10장 실습: FastAPI 모델 서빙.

9장 예고의 실체 — 서빙이 로드하는 것이 바로 `models:/complaint_daily_forecaster@champion`이다.
같은 앱이 두 로드 방식을 지원한다(10.4의 이중 구조).

- 레지스트리 참조(개발 기본값): CH10_MODEL_URI=models:/...@champion — 별칭 이동이 곧 모델 교체
- 이미지 고정(컨테이너):       CH10_MODEL_URI=/app/model — 빌드 시점 champion이 불변으로 동봉

shadow(10.2): challenger 별칭이 로드되면 /predict마다 조용히 병행 예측해 로그로만
남긴다 — 응답은 항상 champion. 반려된 후보(9장 v2)를 실요청 위에서 계속 평가하는 장치다.

실행(호스트): uvicorn app:app --port 8010  (cwd: code/10-1-model-api, chapter10 venv)
"""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

API_DIR = Path(__file__).resolve().parent
# 저장소 배치(code/10-1-model-api/)에서는 chapter10 루트가 기본값의 기준이다.
# 컨테이너(/app)처럼 얕은 배치에서는 parents[1]이 없어 import가 죽는다 — 실제 겪은
# 오류(호스트 통과 후 컨테이너 스모크에서 발견). 컨테이너는 환경변수가 전부
# 지정되므로 기본값 자체가 쓰이지 않는다 — 계산만 안전하게 바꾼다.
BASE_DIR = API_DIR.parents[1] if len(API_DIR.parents) >= 2 else API_DIR

DEFAULT_TRACKING = f"sqlite:///{BASE_DIR / 'data' / 'output' / 'mlflow.db'}"
DEFAULT_MODEL_URI = "models:/complaint_daily_forecaster@champion"
DEFAULT_CHALLENGER = "models:/complaint_daily_forecaster@challenger"
DEFAULT_SHADOW_LOG = str(BASE_DIR / "data" / "output" / "ch10_shadow_log.jsonl")

ALIAS_URI = re.compile(r"^models:/(?P<name>[^/@]+)@(?P<alias>.+)$")


class PredictRequest(BaseModel):
    lawd_cd: str = Field(pattern=r"^\d{5}$", description="법정동코드 5자리(7장 표준코드)")
    x_prev_count: int = Field(ge=0, description="전일 민원 건수(8장 피처)")


class PredictResponse(BaseModel):
    forecast: float
    model_name: str
    model_version: str
    model_source: str


def _load_by_uri(uri: str):
    """모델 URI 하나를 (pyfunc 모델, 신원 dict)로 로드한다."""
    import mlflow
    import mlflow.pyfunc

    m = ALIAS_URI.match(uri)
    if m:  # 레지스트리 별칭 참조 — 버전은 레지스트리에 물어서 답한다
        mlflow.set_tracking_uri(os.environ.get("CH10_TRACKING_URI", DEFAULT_TRACKING))
        model = mlflow.pyfunc.load_model(uri)
        mv = mlflow.MlflowClient().get_model_version_by_alias(m["name"], m["alias"])
        return model, {"model_name": m["name"], "model_version": str(mv.version),
                       "model_source": "registry-alias"}
    # 로컬 디렉터리(이미지 고정) — 신원은 빌드 시 동봉된 export_info.json이 답한다
    model = mlflow.pyfunc.load_model(uri)
    info_path = Path(os.environ.get("CH10_EXPORT_INFO", str(Path(uri) / ".." / "export_info.json")))
    info = json.loads(info_path.resolve().read_text(encoding="utf-8"))
    return model, {"model_name": info["model_name"],
                   "model_version": str(info["champion_version"]),
                   "model_source": "local-dir"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 모델 로드는 시작 시 1회 — 요청마다 로드하면 지연·장애 지점이 요청 경로로 들어온다
    app.state.model, app.state.identity = _load_by_uri(
        os.environ.get("CH10_MODEL_URI", DEFAULT_MODEL_URI))
    challenger_uri = os.environ.get("CH10_CHALLENGER_URI", DEFAULT_CHALLENGER)
    app.state.challenger = None
    if challenger_uri != "off":
        try:
            app.state.challenger, _ = _load_by_uri(challenger_uri)
        except Exception:
            # shadow는 부가 관찰 장치 — challenger가 없어도 서빙 본선은 시작한다
            app.state.challenger = None
    app.state.shadow_log = Path(os.environ.get("CH10_SHADOW_LOG", DEFAULT_SHADOW_LOG))
    yield


app = FastAPI(title="complaint-forecast-api", lifespan=lifespan)


@app.get("/health")
def health():
    """살아 있는가 + 무엇을 서빙 중인가 — 감사 질문 '지금 운영 모델은?'의 API 판."""
    return {"status": "ok", **app.state.identity,
            "shadow_enabled": app.state.challenger is not None}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    x = pd.DataFrame({"x_prev_count": [float(req.x_prev_count)]})
    forecast = float(app.state.model.predict(x)[0])
    if app.state.challenger is not None:
        # shadow: 응답 경로에 영향을 주지 않는 것이 정의다 — 실패해도 본 응답은 나간다
        try:
            shadow = float(app.state.challenger.predict(x)[0])
            entry = {"ts": datetime.now(timezone.utc).isoformat(),
                     "lawd_cd": req.lawd_cd, "x_prev_count": req.x_prev_count,
                     "champion_forecast": round(forecast, 4),
                     "challenger_forecast": round(shadow, 4)}
            app.state.shadow_log.parent.mkdir(parents=True, exist_ok=True)
            with app.state.shadow_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception:
            pass
    return PredictResponse(forecast=round(forecast, 4), **app.state.identity)
