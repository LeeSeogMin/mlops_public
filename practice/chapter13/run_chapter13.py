#!/usr/bin/env python3
"""13주차 통합 실습 오케스트레이션: 통합 MVP의 빌드·기동·시나리오·드릴·검수.

시나리오(본문 실습 14.1)
  0. 사전 점검(docker) + bootstrap(레지스트리 재구성·champion export — 10장 절차)
     + 재조립 확인(app.py sha256 = 10장 파일과 일치)
  1. 이미지 빌드(사전 단계 — 이후 재실행은 빌드 캐시로 빠르다)
  2. 스택 기동(zookeeper·kafka·model-api·processor) + 스모크(/health·6.0·422)
  3. 3일 운영 시뮬레이션: 일별 발행 → 마감 → 집계 확정 → 익일 예측 → 지연 채점
     - 7/2에 중복 재전송 드릴(D2), 7/3에 오염 이벤트 드릴(D1)
  4. 장애 드릴(D3): 7/3 마감 직전 model-api 중단 → 마감은 확정, 예측만 대기
     → 재기동 → 재시도 제어 이벤트 → 수렴
  5. monitor — 통합 리포트·인수 검수표 생성, 전 항목 통과 확인

실행: python run_chapter13.py            (chapter13 venv, Docker 데몬 필요)
      python run_chapter13.py --keep-up  (종료 후 스택 유지 — 수동 관찰용)
콘솔 전체가 data/output/ch13_run_log.txt에 남는다(재실행 산출물 — 커밋 제외).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MVP_DIR = BASE_DIR / "code" / "13-1-integrated-mvp"
OUT_DIR = BASE_DIR / "data" / "output"
MVP_OUT = OUT_DIR / "mvp"
REPO_ROOT = BASE_DIR.parents[1]
CH10_APP = REPO_ROOT / "practice" / "chapter10" / "code" / "10-1-model-api" / "app.py"
API_URL = "http://127.0.0.1:8014"
DAYS = ["2026-07-01", "2026-07-02", "2026-07-03"]

LOG_PATH = OUT_DIR / "ch13_run_log.txt"
_log_fh = None


def say(*args) -> None:
    """print + 실행 로그 보존 — 본문 인용 실측(지연 등)의 원천."""
    line = " ".join(str(a) for a in args)
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return sh(["docker", "compose", *args], cwd=MVP_DIR, check=check)


def service_running(name: str) -> bool:
    r = compose("ps", "-q", name, check=False)
    cid = r.stdout.strip()
    if not cid:
        return False
    r = sh(["docker", "inspect", "-f", "{{.State.Running}}", cid], check=False)
    return r.stdout.strip() == "true"


def wait_file(path: Path, timeout_s: float = 90.0, service: str = "processor") -> None:
    """산출물 폴링 — '죽은 서비스'와 '느린 처리'를 구분한다(10장 교훈)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            return
        if not service_running(service):
            logs = compose("logs", "--no-color", "--tail", "40", service, check=False)
            say(logs.stdout[-2000:])
            raise RuntimeError(f"{service} 컨테이너가 죽었다 — 위 로그를 확인하라")
        time.sleep(0.5)
    raise TimeoutError(f"{path} 생성 대기 시간 초과")


def wait_health(client, timeout_s: float = 90.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last_err = None
    while time.monotonic() < deadline:
        if not service_running("model-api"):
            logs = compose("logs", "--no-color", "--tail", "40", "model-api", check=False)
            say(logs.stdout[-2000:])
            raise RuntimeError("model-api 컨테이너가 죽었다 — 위 로그를 확인하라")
        try:
            r = client.get(f"{API_URL}/health")
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise TimeoutError(f"{API_URL}/health 응답 없음: {last_err}")


def ingest(*args: str) -> None:
    r = compose("run", "--rm", "ingester", *args, check=False)
    say(r.stdout.strip())
    if r.returncode != 0:
        say(r.stderr[-2000:])
        raise RuntimeError(f"ingester 실패: {args}")


def read_snapshot() -> list[dict]:
    return json.loads((MVP_OUT / "predictions_snapshot.json").read_text(encoding="utf-8"))


def main() -> int:
    global _log_fh
    import httpx

    keep_up = "--keep-up" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _log_fh = LOG_PATH.open("w", encoding="utf-8")

    # ── 0. 사전 점검 + bootstrap + 재조립 확인 ──
    say("== 0. 사전 점검·bootstrap·재조립 확인 ==")
    info = sh(["docker", "info", "--format", "{{.ServerVersion}}"], check=False)
    if info.returncode != 0:
        say("  docker 데몬에 연결할 수 없다 — Docker를 켜고 다시 실행하라(부록 A)")
        say("CH13_RUN_FAIL")
        return 1
    say(f"  docker server {info.stdout.strip()}")

    boot = sh([sys.executable, str(MVP_DIR / "model-api" / "bootstrap_registry.py")], check=False)
    say(boot.stdout.strip())
    if boot.returncode != 0 or "CH13_BOOTSTRAP_OK" not in boot.stdout:
        say(boot.stderr[-2000:])
        say("CH13_RUN_FAIL")
        return 1

    app_sha = hashlib.sha256((MVP_DIR / "model-api" / "app.py").read_bytes()).hexdigest()
    ch10_sha = hashlib.sha256(CH10_APP.read_bytes()).hexdigest()
    say(f"  서빙 앱 재조립 확인: sha256 {'일치' if app_sha == ch10_sha else '불일치!'}"
        f" ({app_sha[:16]}…)")
    if app_sha != ch10_sha:
        say("CH13_RUN_FAIL")
        return 1

    # ── 1. 초기화 + 이미지 빌드(사전 단계) ──
    say("\n== 1. 스택 초기화·이미지 빌드 ==")
    compose("down", "-v", "--remove-orphans", check=False)
    if MVP_OUT.exists():
        shutil.rmtree(MVP_OUT)
    MVP_OUT.mkdir(parents=True)

    t0 = time.monotonic()
    build = compose("build", check=False)
    if build.returncode != 0:
        say(build.stdout[-2000:], build.stderr[-2000:])
        say("CH13_RUN_FAIL")
        return 1
    say(f"  빌드 완료 ({time.monotonic() - t0:.0f}s — 캐시 상태에 따라 변동)")
    for img in ("ch13-model-api", "ch13-pipeline"):
        size = sh(["docker", "image", "inspect", img, "--format", "{{.Size}}"]).stdout.strip()
        say(f"  이미지 {img}: {int(size) / 1e6:.0f} MB (환경·시점에 따라 변동)")

    try:
        # ── 2. 기동 + 스모크 ──
        say("\n== 2. 스택 기동·스모크 ==")
        up = compose("up", "-d", "zookeeper", "kafka", "model-api", "processor", check=False)
        if up.returncode != 0:
            say(up.stderr[-2000:])
            say("CH13_RUN_FAIL")
            return 1
        with httpx.Client(timeout=10.0) as client:
            health = wait_health(client)
            say(f"  health={health}")
            t0 = time.monotonic()
            ok = client.post(f"{API_URL}/predict", json={"lawd_cd": "11680", "x_prev_count": 9})
            ms = (time.monotonic() - t0) * 1000
            bad = client.post(f"{API_URL}/predict", json={"lawd_cd": "11680", "x_prev_count": -1})
            say(f"  predict(전일 9) → {ok.json().get('forecast')} ({ms:.1f}ms)"
                f" / 잘못된 입력 → {bad.status_code}")
        smoke = {"health": health, "forecast": ok.json().get("forecast"),
                 "predict_status": ok.status_code, "invalid_input_status": bad.status_code}
        (OUT_DIR / "ch13_smoke.json").write_text(
            json.dumps(smoke, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")

        # ── 3. 3일 운영 시뮬레이션(+드릴 D1·D2 주입) ──
        say("\n== 3. 3일 운영 시뮬레이션 ==")
        say("-- 1일차(2026-07-01): 정상 --")
        ingest("--day", "2026-07-01")
        ingest("--control", "day_close", "--date", "2026-07-01")
        wait_file(MVP_OUT / "daily" / "2026-07-01" / "_SUCCESS")

        say("-- 2일차(2026-07-02): 드릴 D2 — 마지막 10건 재전송(at-least-once) --")
        ingest("--day", "2026-07-02", "--resend-last", "10")
        ingest("--control", "day_close", "--date", "2026-07-02")
        wait_file(MVP_OUT / "daily" / "2026-07-02" / "_SUCCESS")

        say("-- 3일차(2026-07-03): 드릴 D1 — 오염 이벤트 1건 주입 --")
        ingest("--day", "2026-07-03", "--poison", "1")

        # ── 4. 드릴 D3: 마감 직전 모델 API 중단 → 부분 실패 격리 → 복구 ──
        say("\n== 4. 드릴 D3: 모델 API 중단 중 마감 ==")
        compose("stop", "model-api")
        say("  model-api 중단됨 — 이 상태로 7/3 마감을 진행한다")
        ingest("--control", "day_close", "--date", "2026-07-03")
        wait_file(MVP_OUT / "daily" / "2026-07-03" / "_SUCCESS")
        snap = read_snapshot()
        pending = [p for p in snap if p["status"] == "pending_retry"]
        say(f"  마감 확정(_SUCCESS) + 예측 대기 {len(pending)}건"
            f" (오류: {sorted({p['error'] for p in pending})})")
        # 대기 상태 스냅샷을 증거로 보존 — 복구 후 스냅샷은 덮어써진다
        shutil.copyfile(MVP_OUT / "predictions_snapshot.json",
                        MVP_OUT / "predictions_snapshot_pending.json")

        say("  model-api 재기동 → 재시도 제어 이벤트")
        compose("start", "model-api")
        with httpx.Client(timeout=10.0) as client:
            wait_health(client)
        ingest("--control", "predict_retry")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            snap = read_snapshot()
            if not [p for p in snap if p["status"] == "pending_retry"]:
                break
            if not service_running("processor"):
                raise RuntimeError("processor 컨테이너가 죽었다")
            time.sleep(0.5)
        else:
            raise TimeoutError("재시도 수렴 대기 시간 초과")
        say(f"  복구 수렴: 대기 0건, ok {len([p for p in snap if p['status'] == 'ok'])}건")

        # ── 5. monitor: 통합 리포트·인수 검수표 ──
        say("\n== 5. 통합 리포트·인수 검수표 생성 ==")
        mon = sh([sys.executable, str(MVP_DIR / "monitor.py")], check=False)
        say(mon.stdout.strip())
        if mon.returncode != 0:
            say(mon.stderr[-2000:])
            say("CH13_RUN_FAIL")
            return 1

        # processor 관찰 로그(마감·예측 지연 실측)를 실행 로그에 보존
        logs = compose("logs", "--no-color", "processor", check=False)
        say("\n== processor 관찰 로그(발췌 아님 — 전체) ==")
        say(logs.stdout)

        say(f"증거 파일: {OUT_DIR / 'ch13_integration_report.json'}")
        say("CH13_RUN_PASS")
        return 0
    finally:
        if keep_up:
            say("(--keep-up: 스택 유지 — 수동 정리: docker compose -p ch13-mvp down -v)")
        else:
            compose("down", "-v", "--remove-orphans", check=False)
        _log_fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
