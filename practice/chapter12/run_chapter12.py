#!/usr/bin/env python3
"""12장 실습 12.1 오케스트레이션: 모델 API 부하 테스트.

부하 대상은 10장에서 배포한 그 서빙 API(app.py 바이트 동일 복사 — sha256 대조)다.
전 시나리오를 한 번에 재현 실행하고 증거 JSON(ch12_load_report.json)을 남긴다.

시나리오
  0. sha256 대조 — 서빙 앱이 10장 파일과 바이트 동일함을 값으로 확인(재조립 증명)
  1. bootstrap — 9·10장과 동일 절차로 레지스트리 재구성(지문 확인), champion=v1(6.0)
  2. baseline(workers=1, shadow=off) — 기준 부하 + psutil CPU/메모리 병행 샘플링
  3. ramp(workers=1)   — 단계 증가로 knee 관찰(동시성↑ 시 p95↑)
  4. spike(workers=1)  — 재난 급증 시 꼬리 p99·회복(14장 회수)
  5. scale(workers=2)  — 12.4 워커 증설의 처리량 델타
  6. io(workers=1, shadow=on) — 12.3 요청당 파일 I/O(shadow 로그)의 처리량 델타

결정적 값(전 요청 6.0·failures==0·지문·워커 수)만 CH12_RUN_PASS 게이트에 쓰고,
지연 ms·RPS·CPU%는 "특정 실행의 스냅샷"으로 기록한다(재실행마다 변동).

실행: cd practice/chapter12 && venv/bin/python run_chapter12.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR / "code" / "12-1-model-api"
OUTPUT_DIR = BASE_DIR / "data" / "output"
LOCUSTFILE = BASE_DIR / "code" / "12-1-load-test.py"
REPO_ROOT = BASE_DIR.parents[1]
CH10_APP = REPO_ROOT / "practice" / "chapter10" / "code" / "10-1-model-api" / "app.py"

PORT = 8012
MODEL_URI = "models:/complaint_daily_forecaster@champion"
CHALLENGER_URI = "models:/complaint_daily_forecaster@challenger"
TRACKING_URI = f"sqlite:///{OUTPUT_DIR / 'mlflow.db'}"
SHADOW_LOG = OUTPUT_DIR / "ch12_shadow_log.jsonl"
TMP = OUTPUT_DIR / "_locust_tmp"

# 부하 시나리오 — 사용자 수(u)/spawn-rate(r)/지속(t초). closed-loop(wait=0)이라 u가 유효 동시성.
RUNS = [
    {"name": "baseline", "workers": 1, "shadow": False, "u": 20, "r": 20, "t": 12},
    {"name": "ramp", "workers": 1, "shadow": False, "u": 50, "r": 5, "t": 24},
    {"name": "spike", "workers": 1, "shadow": False, "u": 100, "r": 100, "t": 12},
    {"name": "scale", "workers": 2, "shadow": False, "u": 20, "r": 20, "t": 12},
    {"name": "io", "workers": 1, "shadow": True, "u": 20, "r": 20, "t": 12},
]


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def start_uvicorn(workers: int, shadow: bool) -> subprocess.Popen:
    env = dict(os.environ)
    env["CH10_MODEL_URI"] = MODEL_URI
    env["CH10_TRACKING_URI"] = TRACKING_URI
    env["CH10_CHALLENGER_URI"] = CHALLENGER_URI if shadow else "off"
    env["CH10_SHADOW_LOG"] = str(SHADOW_LOG)
    cmd = [sys.executable, "-m", "uvicorn", "app:app", "--port", str(PORT), "--workers", str(workers)]
    # 자체 프로세스 그룹으로 띄운다(POSIX) — --workers가 낳는 워커 자식까지 그룹 단위로
    # 정리하기 위함(강제 종료 시 워커 orphan 방지, stop_server 참조)
    kwargs = {"start_new_session": True} if os.name == "posix" else {}
    return subprocess.Popen(cmd, cwd=API_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def stop_server(proc: subprocess.Popen) -> None:
    """uvicorn 마스터+워커를 프로세스 그룹 단위로 정리한다(--workers 자식 orphan 방지).

    POSIX에서는 프로세스 그룹에 신호를 보내 워커까지 함께 종료하고, kill 후 wait로
    좀비를 재수거한다. 비POSIX에서는 단일 프로세스 종료로 폴백한다.
    """
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    else:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def wait_health(client, proc: subprocess.Popen, timeout_s: float = 60.0) -> dict:
    """'죽은 서버'와 '느린 기동'을 구분한다(10장 교훈) — proc 생존을 함께 확인."""
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("uvicorn 프로세스가 기동 중 종료됨 — 로그 확인")
        try:
            r = client.get(f"http://127.0.0.1:{PORT}/health")
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            last = e
        time.sleep(0.3)
    raise TimeoutError(f"/health 응답 없음: {last}")


def server_tree(pid: int):
    """uvicorn 마스터 + 워커 프로세스 목록(psutil.Process)."""
    import psutil

    try:
        master = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []
    procs = [master]
    try:
        procs += master.children(recursive=True)
    except psutil.Error:
        pass
    return procs


def run_locust_with_sampling(cfg: dict, proc: subprocess.Popen) -> dict:
    """locust headless 실행 + 실행 중 서버 프로세스 트리의 CPU%·RSS 샘플링."""
    import psutil

    prefix = TMP / f"locust_{cfg['name']}"
    cmd = [
        sys.executable, "-m", "locust", "-f", str(LOCUSTFILE), "--headless",
        "-H", f"http://127.0.0.1:{PORT}", "-u", str(cfg["u"]), "-r", str(cfg["r"]),
        "-t", f"{cfg['t']}s", "--csv", str(prefix), "--csv-full-history", "--only-summary",
    ]
    lp = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # cpu_percent(None)은 같은 Process 객체에서 직전 호출 이후를 측정한다 — 매번 새
    # 객체를 만들면 항상 0이 나온다. pid별로 객체를 지속 보관하고 최초 1회 프라이밍한다.
    tracked: dict = {}  # pid -> primed psutil.Process

    def refresh_tracked():
        for p in server_tree(proc.pid):  # 워커는 기동 직후 나타날 수 있어 매번 갱신
            if p.pid not in tracked:
                try:
                    p.cpu_percent(None)  # 프라이밍(첫 값 0 폐기)
                    tracked[p.pid] = p
                except psutil.Error:
                    pass

    cpu_samples, rss_samples = [], []
    try:
        refresh_tracked()
        while lp.poll() is None:
            time.sleep(0.5)
            refresh_tracked()
            cpu_total, rss_total, dead = 0.0, 0, []
            for pid, p in tracked.items():
                try:
                    cpu_total += p.cpu_percent(None)
                    rss_total += p.memory_info().rss
                except psutil.Error:
                    dead.append(pid)
            for pid in dead:
                tracked.pop(pid, None)
            if rss_total > 0:
                cpu_samples.append(cpu_total)
                rss_samples.append(rss_total)
        lp.wait()
    finally:
        # 샘플링 중 예외가 나도 부하 생성기를 남기지 않는다(병렬 세션 오염·orphan 방지)
        if lp.poll() is None:
            lp.terminate()
            try:
                lp.wait(timeout=10)
            except subprocess.TimeoutExpired:
                lp.kill()
                lp.wait()  # kill 후 재수거(좀비 방지)

    stats = parse_stats(Path(f"{prefix}_stats.csv"))
    stats["cpu_pct_peak"] = round(max(cpu_samples), 1) if cpu_samples else None
    stats["cpu_pct_mean"] = round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else None
    stats["rss_mb_peak"] = round(max(rss_samples) / 1e6, 1) if rss_samples else None
    return stats


def _num(row: dict, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "N/A"):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def parse_stats(path: Path) -> dict:
    """locust _stats.csv의 Aggregated 행에서 처리량·지연 분위수를 뽑는다."""
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Aggregated 행이 없으면 조용히 오측정하지 말고 즉시 실패한다(CSV 형식 변화 방어)
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    if agg is None:
        raise RuntimeError(f"locust CSV에 Aggregated 행이 없다: {path}")
    return {
        "requests": int(_num(agg, "Request Count") or 0),
        "failures": int(_num(agg, "Failure Count") or 0),
        "rps": round(_num(agg, "Requests/s") or 0.0, 1),
        "p50_ms": round(_num(agg, "50%") or 0.0, 1),
        "p95_ms": round(_num(agg, "95%") or 0.0, 1),
        "p99_ms": round(_num(agg, "99%") or 0.0, 1),
        "avg_ms": round(_num(agg, "Average Response Time") or 0.0, 1),
        "max_ms": round(_num(agg, "Max Response Time") or 0.0, 1),
    }


def parse_knee(name: str) -> list:
    """ramp의 _stats_history.csv에서 (동시 사용자 수 → p95) 궤적을 뽑는다."""
    path = TMP / f"locust_{name}_stats_history.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Name") == "Aggregated"]
    knee, seen = [], set()
    for r in rows:
        users = int(_num(r, "User Count") or 0)
        p95 = _num(r, "95%")
        if users == 0 or p95 is None or users in seen:
            continue
        seen.add(users)
        knee.append({"users": users, "p95_ms": round(p95, 1)})
    return knee


def main() -> int:
    import httpx

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)

    # ── 시나리오 0: sha256 대조 — 서빙 앱이 10장 파일과 바이트 동일한가 ──
    app_sha = sha256_file(API_DIR / "app.py")
    ch10_sha = sha256_file(CH10_APP)
    print(f"== 시나리오 0: 서빙 앱 재조립 확인 ==")
    print(f"  app.py sha256 {'일치' if app_sha == ch10_sha else '불일치!'} (10장 파일과 바이트 동일)")

    # ── 시나리오 1: bootstrap ──
    print("== 시나리오 1: 레지스트리 재구성(bootstrap) ==")
    boot = subprocess.run([sys.executable, str(API_DIR / "bootstrap_registry.py")],
                          capture_output=True, text=True)
    print(boot.stdout, end="")
    if boot.returncode != 0 or "CH12_BOOTSTRAP_OK" not in boot.stdout:
        print(boot.stderr)
        print("CH12_RUN_FAIL")
        return 1
    summary = json.loads((OUTPUT_DIR / "ch12_bootstrap_summary.json").read_text(encoding="utf-8"))

    # ── 시나리오 2~6: 부하 ──
    scenarios: dict = {}
    for cfg in RUNS:
        print(f"\n== 부하: {cfg['name']} (workers={cfg['workers']}, shadow={cfg['shadow']}, "
              f"u={cfg['u']}, t={cfg['t']}s) ==")
        if SHADOW_LOG.exists():
            SHADOW_LOG.unlink()
        proc = start_uvicorn(cfg["workers"], cfg["shadow"])
        try:
            with httpx.Client(timeout=10.0) as client:
                health = wait_health(client, proc)
            stats = run_locust_with_sampling(cfg, proc)
        finally:
            stop_server(proc)  # 프로세스 그룹 단위 정리(워커 orphan 방지)
        rec = {"workers": cfg["workers"], "shadow": cfg["shadow"], "users": cfg["u"],
               "duration_s": cfg["t"], **stats}
        if cfg["name"] == "ramp":
            rec["knee"] = parse_knee("ramp")
        if cfg["name"] == "io":
            rec["shadow_log_lines"] = (len(SHADOW_LOG.read_text(encoding="utf-8").splitlines())
                                       if SHADOW_LOG.exists() else 0)
        scenarios[cfg["name"]] = rec
        print(f"  requests={rec['requests']} failures={rec['failures']} rps={rec['rps']} "
              f"p50={rec['p50_ms']}ms p95={rec['p95_ms']}ms p99={rec['p99_ms']}ms "
              f"cpu_peak={rec['cpu_pct_peak']}% rss_peak={rec['rss_mb_peak']}MB")

    # ── 관찰 도출(방향성) ──
    base_rps = scenarios["baseline"]["rps"] or 1e-9
    findings = {
        "total_failures": sum(s["failures"] for s in scenarios.values()),
        "all_forecasts_correct": all(s["failures"] == 0 for s in scenarios.values()),
        "scale_vs_baseline": {
            "baseline_rps": scenarios["baseline"]["rps"],
            "workers2_rps": scenarios["scale"]["rps"],
            "ratio": round(scenarios["scale"]["rps"] / base_rps, 2),
            "workers_raise_throughput": scenarios["scale"]["rps"] > scenarios["baseline"]["rps"],
        },
        "io_vs_baseline": {
            "baseline_rps": scenarios["baseline"]["rps"],
            "shadow_on_rps": scenarios["io"]["rps"],
            "ratio": round(scenarios["io"]["rps"] / base_rps, 2),
            "shadow_io_lowers_throughput": scenarios["io"]["rps"] < scenarios["baseline"]["rps"],
        },
        "spike_tail": {
            "p50_ms": scenarios["spike"]["p50_ms"],
            "p99_ms": scenarios["spike"]["p99_ms"],
            "p99_over_p50": round(scenarios["spike"]["p99_ms"] / (scenarios["spike"]["p50_ms"] or 1e-9), 1),
        },
    }

    # locust는 import 시 gevent monkey-patch를 하므로 본체에서 임포트하지 않는다
    from importlib.metadata import version as pkg_version

    import fastapi, mlflow, psutil, sklearn, uvicorn  # noqa: E401
    locust_ver = pkg_version("locust")
    report = {
        "versions": {"locust": locust_ver, "psutil": psutil.__version__,
                     "fastapi": fastapi.__version__, "uvicorn": uvicorn.__version__,
                     "mlflow": mlflow.__version__, "sklearn": sklearn.__version__,
                     "python": sys.version.split()[0]},
        "app_sha256": app_sha,
        "app_sha256_matches_ch10": app_sha == ch10_sha,
        "bootstrap": summary,
        "load_generator": f"locust {locust_ver}, closed-loop(wait_time=0)",
        "cpu_count": psutil.cpu_count(),
        "scenarios": scenarios,
        "findings": findings,
    }
    dump = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    (OUTPUT_DIR / "ch12_load_report.json").write_text(dump, encoding="utf-8")
    shutil.rmtree(TMP, ignore_errors=True)

    # ── 결정적 게이트만 CH12_RUN_PASS 판정에 쓴다(비결정 수치는 스냅샷) ──
    ok = (
        report["app_sha256_matches_ch10"]
        and summary["fingerprint_matches_ch9"]
        and summary["champion_check_forecast"] == 6.0
        and summary["champion_version"] == 1
        and findings["total_failures"] == 0
        and all(s["requests"] > 0 for s in scenarios.values())
        and scenarios["scale"]["workers"] == 2
        and scenarios["io"]["shadow_log_lines"] > 0
    )
    print(f"\n증거 파일: {OUTPUT_DIR / 'ch12_load_report.json'}")
    print("CH12_RUN_" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
