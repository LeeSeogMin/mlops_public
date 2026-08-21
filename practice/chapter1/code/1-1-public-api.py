#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1-1-public-api.py
제1장 실습 1.1 — 공개 API 응답 구조 확인 및 JSON 탐색

기본 동작은 한국환경공단 에어코리아 "대기오염정보"(시도별 실시간 측정정보)
오픈 API를 실제로 호출하여, 공공 API 응답의 실제 구조를 확인하고
측정소 단위 레코드를 요약한다.

인증키는 다음 순서로 읽는다.
  1) --api-key 인자
  2) 환경변수 DATA_GO_KR_API_KEY
  3) (둘 다 없고 --simulate 지정 시) 재현용 시뮬레이터로 대체

실행 예시(실제 API):
    cd practice/chapter1
    export DATA_GO_KR_API_KEY="..."      # Windows(PowerShell): $env:DATA_GO_KR_API_KEY="..."
    python3 -m venv venv && source venv/bin/activate
    pip install -r code/requirements.txt
    python3 code/1-1-public-api.py --sido 서울 --rows 100

실행 예시(오프라인 재현용 시뮬레이터):
    python3 code/1-1-public-api.py --simulate --count 30 --seed 42

주의: 시뮬레이터 출력은 source="simulator"로 표기되며, 실제 API 결과가 아니다.
본문에는 source="live" 결과만 "실제 실행 결과"로 인용한다.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"

# 에어코리아 대기오염정보: 시도별 실시간 측정정보 조회
AIRKOREA_ENDPOINT = (
    "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
)

# 시뮬레이터용 상수(실제 API 미사용 시에만 쓰임)
SIM_REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "경기", "강원"]
SIM_ISSUES = ["교통", "소음", "폐기물", "안전", "시설"]


@dataclass(frozen=True)
class FetchResult:
    source: str  # "live" | "simulator"
    records: list[dict[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_api_key(cli_key: str | None) -> str | None:
    return cli_key or os.environ.get("DATA_GO_KR_API_KEY")


def fetch_airkorea(api_key: str, sido: str, rows: int) -> dict[str, Any]:
    """에어코리아 시도별 실시간 측정정보를 호출해 원본 JSON(payload)을 반환한다."""
    try:
        import requests  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "실제 API 호출에는 `requests`가 필요합니다. "
            "`pip install -r code/requirements.txt`를 먼저 실행하세요."
        ) from e

    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "numOfRows": str(rows),
        "pageNo": "1",
        "sidoName": sido,
        "ver": "1.0",
    }
    resp = requests.get(AIRKOREA_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """에어코리아 표준 응답 구조 response.body.items 에서 레코드 배열을 추출한다."""
    body = (payload or {}).get("response", {}).get("body", {})
    items = body.get("items")
    if isinstance(items, list):
        return [r for r in items if isinstance(r, dict)]
    raise ValueError(
        "예상한 응답 구조가 아닙니다(response.body.items 없음). "
        f"header={payload.get('response', {}).get('header')}"
    )


def to_float(value: Any) -> float | None:
    """'33', '-', '', None 등 혼재된 측정값을 안전하게 float 또는 None으로 변환한다."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def summarize_live(items: list[dict[str, Any]]) -> dict[str, Any]:
    """측정소 레코드를 요약한다: 측정소 수, 결측, PM10/PM2.5 평균, 측정시각 범위."""
    pm10 = [v for v in (to_float(r.get("pm10Value")) for r in items) if v is not None]
    pm25 = [v for v in (to_float(r.get("pm25Value")) for r in items) if v is not None]
    data_times = sorted({str(r.get("dataTime", "")).strip() for r in items if r.get("dataTime")})

    def avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 1) if xs else None

    return {
        "generated_at": utc_now_iso(),
        "source": "live",
        "endpoint": AIRKOREA_ENDPOINT,
        "station_count": len(items),
        "pm10_reported": len(pm10),
        "pm25_reported": len(pm25),
        "pm10_missing": len(items) - len(pm10),
        "pm25_missing": len(items) - len(pm25),
        "pm10_avg": avg(pm10),
        "pm25_avg": avg(pm25),
        "data_time_min": data_times[0] if data_times else None,
        "data_time_max": data_times[-1] if data_times else None,
        "sample_station": items[0].get("stationName") if items else None,
        "available_fields": sorted(items[0].keys()) if items else [],
    }


def generate_sim_records(count: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for i in range(count):
        out.append(
            {
                "event_time": utc_now_iso(),
                "region_name": rng.choice(SIM_REGIONS),
                "issue_name": rng.choice(SIM_ISSUES),
                "content_length": rng.randint(20, 500),
            }
        )
    return out


def summarize_sim(records: list[dict[str, Any]]) -> dict[str, Any]:
    region_counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for r in records:
        region_counts[r["region_name"]] = region_counts.get(r["region_name"], 0) + 1
        issue_counts[r["issue_name"]] = issue_counts.get(r["issue_name"], 0) + 1
    return {
        "generated_at": utc_now_iso(),
        "source": "simulator",
        "total_records": len(records),
        "region_counts": dict(sorted(region_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "issue_counts": dict(sorted(issue_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Chapter 1 practice 1.1: public API response inspection")
    parser.add_argument("--sido", default="서울", help="시도명 (실제 API 조회 대상)")
    parser.add_argument("--rows", type=int, default=100, help="조회 행 수(numOfRows)")
    parser.add_argument("--api-key", default=None, help="공공데이터포털 인증키(미지정 시 DATA_GO_KR_API_KEY 사용)")
    parser.add_argument("--simulate", action="store_true", help="실제 API 대신 재현용 시뮬레이터 사용")
    parser.add_argument("--count", type=int, default=30, help="[시뮬레이터] 생성 건수")
    parser.add_argument("--seed", type=int, default=42, help="[시뮬레이터] 재현성 시드")
    args = parser.parse_args(argv)

    if args.simulate:
        records = generate_sim_records(args.count, args.seed)
        summary = summarize_sim(records)
        out_path = OUTPUT_DIR / "ch1_api_summary_sim.json"
        write_json(out_path, summary)
        print(f"source=simulator total_records={summary['total_records']} output={out_path}")
        return 0

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print(
            "인증키가 없습니다. --api-key 를 주거나 DATA_GO_KR_API_KEY 환경변수를 설정하세요.\n"
            "오프라인 재현은 --simulate 를 사용합니다.",
            file=sys.stderr,
        )
        return 2

    payload = fetch_airkorea(api_key, sido=args.sido, rows=args.rows)
    items = extract_items(payload)
    summary = summarize_live(items)

    out_path = OUTPUT_DIR / "ch1_api_summary.json"
    write_json(out_path, summary)

    print(
        f"source=live stations={summary['station_count']} "
        f"pm10_avg={summary['pm10_avg']} pm25_avg={summary['pm25_avg']} output={out_path}"
    )
    if items:
        print("\n[first_record]")
        print(json.dumps(items[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
