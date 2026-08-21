"""12장 실습: 모델 API 부하 시나리오(locustfile).

부하 대상은 10장에서 배포한 그 서빙 API(app.py 바이트 동일 복사)다. 가상 사용자는
champion(상수 예측기)에게 강남구 전일 9건을 반복해서 물어본다 — 응답은 언제나 6.0이어야
한다. 이 locustfile의 핵심은 성능 수치가 아니라 **정확성 검증**이다: 부하가 아무리 세도
응답이 6.0이 아니거나 200이 아니면 그 요청을 실패로 표시한다. 그래서 failures==0은
"오류 없음"과 "전 요청이 옳은 답"을 동시에 보증한다.

실행은 run_chapter12.py가 headless로 호출한다(웹 UI 없음, --csv로 통계 저장):
  locust -f 12-1-load-test.py --headless -H http://127.0.0.1:8012 \
         -u <users> -r <spawn> -t <sec>s --csv <prefix> --only-summary
"""

from __future__ import annotations

from locust import HttpUser, constant, task

# 8장 온라인 스토어 실측값(강남구 전일 건수 9) — 10장 스모크와 같은 앵커 입력
PAYLOAD = {"lawd_cd": "11680", "x_prev_count": 9}
EXPECTED_FORECAST = 6.0  # champion(v1)=평균 예측기 → 훈련 y 평균 36/6=6.0(9장 검산)


class ForecastUser(HttpUser):
    # wait_time=0: 각 사용자는 대기 없이 다음 요청을 보낸다(closed-loop).
    # 사용자 수 N이 곧 유효 동시성 L이 되어 Little's law(L=λ·W)를 깔끔히 시연한다.
    wait_time = constant(0)

    @task
    def predict(self):
        with self.client.post("/predict", json=PAYLOAD, catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"status={r.status_code}")
                return
            forecast = r.json().get("forecast")
            if forecast != EXPECTED_FORECAST:
                # 부하 중 오답은 성능 저하보다 먼저 봐야 할 신호다
                r.failure(f"forecast={forecast} (expected {EXPECTED_FORECAST})")
