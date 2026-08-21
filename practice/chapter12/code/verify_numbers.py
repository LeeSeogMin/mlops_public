#!/usr/bin/env python3
"""12장 수치 대조: 본문(docs/chapter12.md) 인용 수치를 증거 JSON과 전수 대조한다.

지연 ms·RPS·CPU% 등은 재실행마다 변한다 — 코드를 고쳐 재실행하면 본문 수치도 전수
갱신해야 한다. 이 스크립트는 증거 JSON(ch12_load_report.json)에서 본문이 인용하는
값을 형식대로 만들어, 그 문자열이 실제로 본문에 있는지 확인한다(잔존 낡은 수치 사냥).

실행: cd practice/chapter12 && venv/bin/python code/verify_numbers.py
출력 마지막 줄이 ALL_PASS면 통과.
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REPORT = BASE / "data" / "output" / "ch12_load_report.json"
DOC = BASE.parents[1] / "docs" / "chapter12.md"


def g(v) -> str:
    """숫자를 본문 표기 형식으로(정수는 정수, 소수는 그대로)."""
    return f"{v:g}"


def main() -> int:
    r = json.loads(REPORT.read_text(encoding="utf-8"))
    if not DOC.exists():
        print(f"본문 없음: {DOC}")
        print("ALL_FAIL")
        return 1
    doc = DOC.read_text(encoding="utf-8")

    s = r["scenarios"]
    checks: list[tuple[str, str]] = []

    # ── 결정적 값(반드시 일치) ──
    checks += [
        ("app sha256 접두", r["app_sha256"][:8]),
        ("데이터 지문 접두", r["bootstrap"]["data_fingerprint_sha256"][:8]),
        ("champion 검증 예측", g(r["bootstrap"]["champion_check_forecast"])),
        ("코어 수", g(r["cpu_count"])),
    ]

    # ── 시나리오별 스냅샷(본문이 인용하면 일치해야 함) ──
    for name in ("baseline", "ramp", "spike", "scale", "io"):
        d = s[name]
        checks.append((f"{name} rps", g(d["rps"])))
        checks.append((f"{name} p50", f"{g(d['p50_ms'])}ms"))
        checks.append((f"{name} p99", f"{g(d['p99_ms'])}ms"))
        checks.append((f"{name} cpu_peak", g(d["cpu_pct_peak"])))

    # 개별 강조 수치
    checks += [
        ("baseline p95", f"{g(s['baseline']['p95_ms'])}ms"),
        ("baseline rss", g(s["baseline"]["rss_mb_peak"])),
        ("baseline avg", g(s["baseline"]["avg_ms"])),
        ("spike p99", f"{g(s['spike']['p99_ms'])}ms"),
        ("spike max", g(s["spike"]["max_ms"])),
        ("scale rss", g(s["scale"]["rss_mb_peak"])),
        ("scale ratio", g(r["findings"]["scale_vs_baseline"]["ratio"])),
        ("io ratio", g(r["findings"]["io_vs_baseline"]["ratio"])),
    ]

    # ── ramp knee 궤적(본문 표에 인용하는 대표점) ──
    knee = {k["users"]: k["p95_ms"] for k in s["ramp"]["knee"]}
    for u in (10, 20, 30, 40, 50):
        if u in knee:
            checks.append((f"knee u={u} p95", f"{g(knee[u])}ms"))

    missing = [(label, val) for label, val in checks if val not in doc]
    for label, val in checks:
        mark = "OK " if val in doc else "MISS"
        print(f"  [{mark}] {label}: '{val}'")
    print(f"\n대조 {len(checks)}건, 불일치 {len(missing)}건")
    if missing:
        print("누락/불일치:")
        for label, val in missing:
            print(f"  - {label}: 본문에서 '{val}'를 찾지 못함")
        print("ALL_FAIL")
        return 1
    print("ALL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
