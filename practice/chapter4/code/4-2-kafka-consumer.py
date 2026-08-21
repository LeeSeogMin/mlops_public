#!/usr/bin/env python3
"""4-2: 민원 이벤트 Kafka Consumer — 커밋 시점과 유실·중복 관찰.

오프셋 커밋 시점을 바꿔 가며 전달 의미론의 차이를 실제로 관찰한다.

  --mode at-least-once : 배치를 "처리한 뒤" 커밋 (기본). 커밋 전 크래시 → 중복.
  --mode at-most-once  : 배치를 "처리하기 전" 커밋. 처리 중 크래시 → 유실.

--crash-after N 을 주면 N건 처리 후 강제 종료(exit 42)로 장애를 흉내 낸다.
처리한 이벤트는 data/output/ch4_processed_{group}.jsonl 에 누적 기록되므로,
크래시 후 재시작하면 같은 파일에서 중복(같은 event_id 재등장)·유실을 셀 수 있다.

실행 예:
    python code/4-2-kafka-consumer.py --group g-demo --mode at-least-once --crash-after 10
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from kafka import KafkaConsumer

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "output"

DEFAULT_TOPIC = "public.complaint.received.v1"
DEFAULT_BOOTSTRAP = "localhost:9092"

CRASH_EXIT_CODE = 42  # 오케스트레이터(run_chapter4.py)가 "의도된 크래시"로 인식


def process_event(event: dict, meta: dict, store_path: Path) -> None:
    """이벤트 '처리' — 처리 기록을 로컬 저장소(JSONL)에 남긴다."""
    record = {**meta, "event_id": event.get("event_id"), "scenario": event.get("scenario")}
    with store_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="민원 이벤트 Consumer")
    parser.add_argument("--bootstrap", default=DEFAULT_BOOTSTRAP)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--group", default="complaint-processor")
    parser.add_argument("--mode", choices=["at-least-once", "at-most-once"], default="at-least-once")
    parser.add_argument("--crash-after", type=int, default=0, help="N건 처리 후 강제 종료(0=끄기)")
    parser.add_argument("--idle-sec", type=float, default=6.0, help="이 시간 동안 새 메시지가 없으면 종료")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    store_path = OUTPUT_DIR / f"ch4_processed_{args.group}.jsonl"

    consumer = KafkaConsumer(
        args.topic,
        bootstrap_servers=args.bootstrap,
        group_id=args.group,
        enable_auto_commit=False,          # 커밋 시점을 코드가 결정한다
        auto_offset_reset="earliest",      # 커밋이 없으면 처음부터 읽는다
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        # 크래시 감지 창: 하트비트가 이 시간 동안 끊기면 브로커가 컨슈머를
        # 그룹에서 제외한다. 크래시 직후 재시작하면 이 시간만큼 파티션
        # 재할당이 늦어질 수 있다(실습 4.1의 재시작 대기가 이 때문).
        session_timeout_ms=10000,
        heartbeat_interval_ms=3000,
    )

    processed = 0
    latencies_ms: list[float] = []
    partitions_seen: Counter = Counter()
    idle_deadline = time.time() + args.idle_sec

    def build_meta(tp, rec) -> dict:
        event = rec.value
        now = time.time()
        return {
            "partition": tp.partition,
            "offset": rec.offset,
            "consumed_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round((now - event["send_ts"]) * 1000, 1)
            if "send_ts" in event else None,
        }

    if args.crash_after:
        # ── 크래시 실험 경로 ────────────────────────────────────────
        # 크래시 시점이 폴링 배치 경계와 우연히 일치하면 "유실 0/중복 0"이
        # 나와 실험 의도가 무산된다. 이를 막기 위해 crash_after보다 많은
        # 레코드를 먼저 확보한 뒤, 일부만 처리하고 죽는다.
        #   at-most-once : 확보한 배치를 전부 커밋해 둔다 → 미처리분 유실
        #   at-least-once: 아무것도 커밋하지 않는다 → 처리분이 재수신(중복)
        pending: list = []
        while time.time() < idle_deadline:
            batch = consumer.poll(timeout_ms=1000)
            if not batch:
                if len(pending) > args.crash_after:
                    break  # 커밋됐지만 미처리로 남을 레코드가 확보됨
                continue
            idle_deadline = time.time() + args.idle_sec
            if args.mode == "at-most-once":
                consumer.commit()  # 처리 "전" 커밋
            for tp, records in batch.items():
                pending.extend((tp, rec) for rec in records)
        if len(pending) <= args.crash_after:
            print(f"[경고] 확보 레코드({len(pending)}) <= crash-after({args.crash_after}) — "
                  f"유실/중복이 관찰되지 않을 수 있음")
        for tp, rec in pending[:args.crash_after]:
            process_event(rec.value, build_meta(tp, rec), store_path)
            processed += 1
        print(f"[크래시 시뮬레이션] {processed}건 처리 후 강제 종료 "
              f"(mode={args.mode}, 확보 {len(pending)}건)")
        os._exit(CRASH_EXIT_CODE)  # close()도 커밋도 없이 즉시 종료

    while time.time() < idle_deadline:
        batch = consumer.poll(timeout_ms=1000)
        if not batch:
            continue
        idle_deadline = time.time() + args.idle_sec

        if args.mode == "at-most-once":
            consumer.commit()  # 처리 "전" 커밋 — 처리 중 크래시 시 이 배치는 유실

        for tp, records in batch.items():
            for rec in records:
                meta = build_meta(tp, rec)
                process_event(rec.value, meta, store_path)
                processed += 1
                partitions_seen[tp.partition] += 1
                if meta["latency_ms"] is not None:
                    latencies_ms.append(meta["latency_ms"])

        if args.mode == "at-least-once":
            consumer.commit()  # 처리 "후" 커밋 — 커밋 전 크래시 시 이 배치는 재수신(중복)

    consumer.close()

    summary = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "topic": args.topic,
        "group": args.group,
        "mode": args.mode,
        "processed_this_run": processed,
        "partitions_seen": {str(p): c for p, c in sorted(partitions_seen.items())},
        "latency_ms": {
            "count": len(latencies_ms),
            "mean": round(sum(latencies_ms) / len(latencies_ms), 1) if latencies_ms else None,
            "max": max(latencies_ms) if latencies_ms else None,
        },
        "processed_store": str(store_path.relative_to(BASE_DIR)),
    }
    out_path = OUTPUT_DIR / f"ch4_consume_{args.group}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[저장] {out_path}")


if __name__ == "__main__":
    main()
