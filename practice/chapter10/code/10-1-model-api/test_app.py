"""10장 실습: 서빙 API 기본 테스트(pytest + TestClient).

서버 프로세스 없이 앱을 직접 검증한다 — CI(10.5)의 첫 게이트.
선행 조건: bootstrap_registry.py 실행(레지스트리·champion 존재).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # 테스트의 shadow 기록은 임시 경로로 — 실측 산출물(data/output)을 오염시키지 않는다
    monkeypatch.setenv("CH10_SHADOW_LOG", str(tmp_path / "shadow.jsonl"))
    from app import app

    with TestClient(app) as c:  # with 블록이 lifespan(모델 로드)을 실행한다
        yield c


def test_health_reports_identity(client):
    """/health는 생존만이 아니라 '무엇을 서빙 중인가'를 답해야 한다."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_name"] == "complaint_daily_forecaster"
    assert body["model_version"] == "1"  # 9장 판정과 동일: champion=v1


def test_predict_known_input_known_output(client):
    """서빙 계약 스모크: 알려진 입력 → 알려진 출력(9장 검산값 6.0)."""
    r = client.post("/predict", json={"lawd_cd": "11680", "x_prev_count": 9})
    assert r.status_code == 200
    assert r.json()["forecast"] == 6.0  # champion(v1)은 평균 예측기 — 훈련 y 평균 36/6


def test_predict_baseline_ignores_input(client):
    """v1의 정의 확인: 평균 예측기는 입력과 무관하게 같은 값을 낸다(9장 관찰의 API 판)."""
    r0 = client.post("/predict", json={"lawd_cd": "11440", "x_prev_count": 0})
    assert r0.json()["forecast"] == 6.0


def test_invalid_input_rejected_422(client):
    """입력 검증이 스키마 계약이다 — 잘못된 입력은 모델에 닿기 전에 거절된다."""
    assert client.post("/predict", json={"lawd_cd": "11680", "x_prev_count": -1}).status_code == 422
    assert client.post("/predict", json={"lawd_cd": "강남구", "x_prev_count": 9}).status_code == 422
    assert client.post("/predict", json={"x_prev_count": 9}).status_code == 422
