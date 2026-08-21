#!/usr/bin/env python3
"""10장 실습 10.1 오케스트레이션: 모델 API 컨테이너 빌드와 호출.

시나리오
  1. bootstrap — 9장과 동일 절차로 레지스트리 재구성(지문 일치 확인), champion export
  2. pytest — TestClient로 서빙 계약 검증(서버 프로세스 없이)
  3. 호스트 서빙 — uvicorn 기동 → /health·/predict·422 실측, shadow 로그 관찰
  4. 컨테이너 — docker build → run → 동일 호출 실측(호스트=컨테이너 동일성) → 정리

CI(GitHub Actions) 워크플로가 실행하는 것도 이 단계들과 같다(10.5).
실행: python run_chapter10.py  [--skip-docker: 1~3단계만 — CH10_RUN_PARTIAL]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR / "code" / "10-1-model-api"
OUTPUT_DIR = BASE_DIR / "data" / "output"
SHADOW_LOG = OUTPUT_DIR / "ch10_shadow_log.jsonl"
REPO_ROOT = BASE_DIR.parents[1]

HOST_PORT = 8010
CONTAINER_PORT = 8011
IMAGE = "ch10-model-api"
CONTAINER = "ch10-model-api"


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def wait_health(client, base_url: str, timeout_s: float = 90.0, alive=None) -> dict:
    """서버가 응답할 때까지 폴링한다.

    '죽은 서버'와 '느린 기동'을 구분한다 — alive 검사 없이 timeout만 기다리면
    import 시점에 즉사한 서버도 90초를 다 기다려야 드러난다(실제 겪은 오류).
    """
    deadline = time.monotonic() + timeout_s
    last_err = None
    while time.monotonic() < deadline:
        if alive is not None and not alive():
            raise RuntimeError(f"{base_url} 서버 프로세스가 종료됨 — 기동 로그를 확인하라")
        try:
            r = client.get(f"{base_url}/health")
            if r.status_code == 200:
                return r.json()
        except Exception as e:  # 기동 전 연결 거부는 정상 경과
            last_err = e
        time.sleep(0.5)
    raise TimeoutError(f"{base_url}/health 응답 없음: {last_err}")


def call_api(client, base_url: str, alive=None) -> dict:
    """실측 호출 세트 — 호스트와 컨테이너에 동일하게 적용한다."""
    health = wait_health(client, base_url, alive=alive)
    ok = client.post(f"{base_url}/predict",
                     json={"lawd_cd": "11680", "x_prev_count": 9})  # 강남 최신 피처(8장 실측 9)
    bad = client.post(f"{base_url}/predict", json={"lawd_cd": "11680", "x_prev_count": -1})
    return {
        "health": health,
        "predict_status": ok.status_code,
        "forecast": ok.json().get("forecast") if ok.status_code == 200 else None,
        "invalid_input_status": bad.status_code,
    }


def dump_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def main() -> int:
    import httpx

    skip_docker = "--skip-docker" in sys.argv

    # ── 시나리오 1: bootstrap ──
    print("== 시나리오 1: 레지스트리 재구성(bootstrap) ==")
    boot = sh([sys.executable, str(API_DIR / "bootstrap_registry.py")], check=False)
    print(boot.stdout, end="")
    if boot.returncode != 0 or "CH10_BOOTSTRAP_OK" not in boot.stdout:
        print(boot.stderr)
        print("CH10_RUN_FAIL")
        return 1
    summary = json.loads((OUTPUT_DIR / "ch10_bootstrap_summary.json").read_text(encoding="utf-8"))

    # ── 시나리오 2: pytest ──
    print("\n== 시나리오 2: 서빙 계약 테스트(pytest) ==")
    py = sh([sys.executable, "-m", "pytest", "-q", str(API_DIR)], cwd=API_DIR, check=False)
    print(py.stdout, end="")
    m = re.search(r"(\d+) passed", py.stdout)
    tests_passed = int(m.group(1)) if m and py.returncode == 0 else 0

    # ── 시나리오 3: 호스트 서빙(uvicorn) — 레지스트리 별칭 참조 ──
    print("\n== 시나리오 3: 호스트 서빙 — models:/...@champion 로드 ==")
    if SHADOW_LOG.exists():
        SHADOW_LOG.unlink()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(HOST_PORT)],
        cwd=API_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(timeout=10.0) as client:
            host = call_api(client, f"http://127.0.0.1:{HOST_PORT}",
                            alive=lambda: proc.poll() is None)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    shadow_entries = [json.loads(l) for l in SHADOW_LOG.read_text(encoding="utf-8").splitlines()] \
        if SHADOW_LOG.exists() else []
    shadow_obs = None
    if shadow_entries:
        e = shadow_entries[-1]
        shadow_obs = {k: e[k] for k in ("lawd_cd", "x_prev_count",
                                        "champion_forecast", "challenger_forecast")}
    print(f"  health={host['health']}")
    print(f"  predict(전일 9) → {host['forecast']} / 잘못된 입력 → {host['invalid_input_status']}")
    print(f"  shadow 관찰: {shadow_obs}")

    # ── 시나리오 4: 컨테이너 — 이미지 고정 모델 ──
    container = {"skipped": True}
    docker_version = None
    if skip_docker:
        print("\n== 시나리오 4: 건너뜀(--skip-docker) ==")
    else:
        print("\n== 시나리오 4: 컨테이너 빌드·기동·호출 ==")
        info = sh(["docker", "info", "--format", "{{.ServerVersion}}"], check=False)
        if info.returncode != 0:
            print("  docker 데몬에 연결할 수 없다 — 실행하려면 Docker를 켜거나 --skip-docker")
            print("CH10_RUN_FAIL")
            return 1
        docker_version = info.stdout.strip()
        build = sh(["docker", "build", "-t", IMAGE, "."], cwd=API_DIR, check=False)
        if build.returncode != 0:
            print(build.stdout[-2000:], build.stderr[-2000:])
            print("CH10_RUN_FAIL")
            return 1
        size = sh(["docker", "image", "inspect", IMAGE, "--format", "{{.Size}}"]).stdout.strip()
        print(f"  이미지 빌드 완료: {IMAGE} ({int(size) / 1e6:.0f} MB — 환경·시점에 따라 변동)")
        sh(["docker", "rm", "-f", CONTAINER], check=False)  # 이전 실행 잔재 정리
        # --rm 없이 띄운다 — 크래시하면 로그가 남아야 진단할 수 있다(정리는 finally에서)
        sh(["docker", "run", "-d", "-p", f"{CONTAINER_PORT}:8000",
            "--name", CONTAINER, IMAGE])

        def container_alive() -> bool:
            r = sh(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER], check=False)
            return r.stdout.strip() == "true"

        try:
            with httpx.Client(timeout=10.0) as client:
                container = call_api(client, f"http://127.0.0.1:{CONTAINER_PORT}",
                                     alive=container_alive)
        except Exception:
            print(sh(["docker", "logs", CONTAINER], check=False).stderr[-2000:])
            raise
        finally:
            sh(["docker", "rm", "-f", CONTAINER], check=False)
        print(f"  health={container['health']}")
        print(f"  predict(전일 9) → {container['forecast']} / 잘못된 입력 → {container['invalid_input_status']}")

    # ── 증거·검수 산출물 ──
    import fastapi, mlflow, sklearn, uvicorn  # noqa: E401 — 버전 기록용
    report = {
        "versions": {"fastapi": fastapi.__version__, "uvicorn": uvicorn.__version__,
                     "mlflow": mlflow.__version__, "sklearn": sklearn.__version__},
        "bootstrap": summary,
        "tests": {"passed": tests_passed},
        "host": host,
        "shadow_observation": shadow_obs,
        "container": container,
        "consistency": {
            "host_forecast": host["forecast"],
            "container_forecast": container.get("forecast"),
            "host_equals_container": container.get("forecast") == host["forecast"],
            "matches_ch9_forecast_6_0": host["forecast"] == 6.0,
        },
    }
    dump_json(OUTPUT_DIR / "ch10_deploy_report.json", report)

    workflow = REPO_ROOT / ".github" / "workflows" / "ch10-model-api.yml"
    checklist = {  # 배포 전 검수 체크리스트(정본 산출물) — 이 실행의 실측에서 도출
        "1_자동_테스트_통과": tests_passed >= 4,
        "2_서빙_신원_응답(/health가 모델 이름·버전을 답함)": host["health"].get("model_version") == "1",
        "3_알려진_입력_알려진_출력_스모크": host["forecast"] == 6.0,
        "4_잘못된_입력_거절(422)": host["invalid_input_status"] == 422,
        "5_컨테이너_호스트_동일_예측(환경_동등성)": container.get("forecast") == host["forecast"],
        "6_모델_실물_이미지_고정_및_출처_동봉": (API_DIR / "model_export" / "export_info.json").exists(),
        "7_레지스트리_버전_보존(롤백_전제)": summary["challenger_version"] == 2,
        "8_검증_파이프라인_정의(CI_워크플로)": workflow.exists(),
    }
    dump_json(OUTPUT_DIR / "ch10_release_checklist.json", checklist)

    ok = (
        summary["fingerprint_matches_ch9"]
        and summary["champion_version"] == 1
        and tests_passed >= 4
        and host["forecast"] == 6.0
        and host["invalid_input_status"] == 422
        and shadow_obs is not None
        and shadow_obs["challenger_forecast"] == 7.3636  # 81/11 — 손 검산(본문)
        and (skip_docker or (container.get("forecast") == 6.0
                             and container["health"]["model_source"] == "local-dir"))
        and all(checklist.values() if not skip_docker else
                [v for k, v in checklist.items() if not k.startswith("5")])
    )
    print(f"\n증거 파일: {OUTPUT_DIR / 'ch10_deploy_report.json'}")
    if ok and skip_docker:
        print("CH10_RUN_PARTIAL (docker 단계 미실행)")
        return 0
    print("CH10_RUN_" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
