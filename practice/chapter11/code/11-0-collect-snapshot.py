#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
11-0-collect-snapshot.py
제11장 보조 — 에어코리아 서울 실시간 스냅샷 수집기(게시 지연 대응 폴러)

목표 정시(dataTime)의 데이터가 게시될 때까지 주기적으로 API를 호출해,
응답의 dataTime이 목표와 일치하는 순간의 원본 응답을 그대로 저장한다.

왜 폴러인가: 에어코리아 정시 데이터는 정시보다 늦게(수 분~수십 분) 게시된다
(2장 수집 당시 23:00 데이터가 23:30 이후 게시된 실측). 로컬 시계가 아니라
응답 안의 dataTime을 확인해야 "몇 시 데이터인가"를 잘못 저장하지 않는다.

인증키: 환경변수 DATA_GO_KR_API_KEY (1장과 동일 — .env에 두고 셸에서 로드,
평문 커밋 금지). 표준 라이브러리만 사용하므로 venv 없이 실행 가능하다.

실행 예 (2026-07-07 22:00 데이터 수집):
    cd practice/chapter11
    python3 code/11-0-collect-snapshot.py \
        --target-datatime "2026-07-07 22:00" \
        --out data/input/airquality_seoul_2200_0707.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

AIRKOREA_ENDPOINT = (
    "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fetch_snapshot(service_key: str, sido: str = "서울", rows: int = 100) -> tuple[str, dict]:
    """API를 1회 호출해 (원본 응답 텍스트, 파싱된 dict)를 돌려준다."""
    params = urllib.parse.urlencode({
        "serviceKey": service_key,
        "returnType": "json",
        "numOfRows": str(rows),
        "pageNo": "1",
        "sidoName": sido,
        "ver": "1.0",
    })
    with urllib.request.urlopen(f"{AIRKOREA_ENDPOINT}?{params}", timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return raw, json.loads(raw)


def latest_datatime(payload: dict) -> str:
    items = payload.get("response", {}).get("body", {}).get("items", [])
    return str(items[0].get("dataTime")) if items else "unknown"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AirKorea Seoul snapshot poller")
    parser.add_argument("--target-datatime", required=True,
                        help='수집할 정시 데이터의 dataTime (예: "2026-07-07 22:00")')
    parser.add_argument("--out", required=True, help="저장 경로(원본 응답 그대로)")
    parser.add_argument("--poll-sec", type=int, default=180, help="폴링 간격(초)")
    parser.add_argument("--deadline-min", type=int, default=100,
                        help="이 시간 안에 목표 dataTime이 안 나오면 실패로 종료")
    args = parser.parse_args(argv)

    service_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not service_key:
        print("환경변수 DATA_GO_KR_API_KEY가 없습니다(.env 로드 필요).", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + args.deadline_min * 60
    attempt = 0
    while True:
        attempt += 1
        try:
            raw, payload = fetch_snapshot(service_key)
            seen = latest_datatime(payload)
        except Exception as e:  # 일시 오류는 다음 폴링에서 재시도
            seen = f"(호출 실패: {e})"
            raw = ""
        print(f"[{attempt:02d}] 최신 dataTime = {seen} (목표 {args.target_datatime})",
              flush=True)
        if seen == args.target_datatime and raw:
            out_path.write_text(raw, encoding="utf-8")
            n = len(payload["response"]["body"]["items"])
            print(f"저장 완료: {out_path} (측정소 {n}개)")
            return 0
        if time.monotonic() >= deadline:
            print("마감 초과 — 목표 정시 데이터가 게시되지 않았습니다.", file=sys.stderr)
            return 1
        time.sleep(args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
