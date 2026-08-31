#!/usr/bin/env python3
"""13주차 통합 MVP: ingester — 민원 이벤트와 제어 이벤트를 Kafka에 발행한다.

접수 채널(웹·전화·현장)을 대신하는 수집기다. 하루치 원천 파일(6주차 커밋 입력)을
`complaints.raw` 토픽으로 흘리고, 일 마감은 같은 토픽의 제어 이벤트(day_close)로
알린다 — 순서 보장을 위해 토픽은 단일 파티션이다(축소 설계 — 본문 14.2).

드릴 주입 플래그(14.5):
  --resend-last N   마지막 N건을 한 번 더 발행(at-least-once 재전송 재현 — 4장)
  --poison N        파싱 불가 페이로드 N건을 이벤트 사이에 발행(오염 이벤트 — 격리 확인)

실행(컨테이너): docker compose run --rm ingester --day 2026-07-01
                docker compose run --rm ingester --control day_close --date 2026-07-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:29092")
TOPIC = os.environ.get("TOPIC", "complaints.raw")
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/in"))

# 오염 이벤트 페이로드 — 결정적(재실행 동일). JSON으로 파싱되지 않는다.
POISON_PAYLOAD = b"{poison: not-json, drill=D1"


def ensure_topic() -> None:
    """토픽을 단일 파티션으로 생성한다. 이미 있으면 파티션 수를 검증한다.

    존재하지 않는 API를 try/except로 감싸 무동작이 침묵하는 사고를 피하기 위해
    (4장 gotcha), 생성 실패 시 파티션 수를 소비자 메타데이터로 직접 확인한다.
    """
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    try:
        admin.create_topics([NewTopic(name=TOPIC, num_partitions=1, replication_factor=1)])
        print(f"[ingester] 토픽 생성: {TOPIC} (partitions=1)")
    except TopicAlreadyExistsError:
        from kafka import KafkaConsumer
        parts = KafkaConsumer(bootstrap_servers=BOOTSTRAP).partitions_for_topic(TOPIC)
        if parts != {0}:
            raise SystemExit(f"토픽 {TOPIC} 파티션이 단일이 아니다: {parts} — 마감 순서 보장 불가")
        print(f"[ingester] 토픽 존재 확인: {TOPIC} (partitions=1)")
    finally:
        admin.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="발행할 날짜(YYYY-MM-DD) — data/input/complaints/{day}.jsonl")
    ap.add_argument("--resend-last", type=int, default=0, help="마지막 N건 재발행(중복 드릴)")
    ap.add_argument("--poison", type=int, default=0, help="오염 이벤트 N건 주입(격리 드릴)")
    ap.add_argument("--control", choices=["day_close", "predict_retry"], help="제어 이벤트 발행")
    ap.add_argument("--date", help="제어 이벤트의 대상 날짜")
    args = ap.parse_args()

    ensure_topic()
    # acks=all: 브로커 수신 확인까지 기다린다(4장 at-least-once 구성과 동일)
    producer = KafkaProducer(bootstrap_servers=BOOTSTRAP, acks="all")

    if args.control:
        if args.control == "day_close" and not args.date:
            raise SystemExit("--control day_close에는 --date가 필요하다")
        msg = {"type": args.control, "date": args.date}
        producer.send(TOPIC, json.dumps(msg, ensure_ascii=False).encode("utf-8"))
        producer.flush()
        print(f"[ingester] 제어 이벤트 발행: {msg}")
        return 0

    if not args.day:
        raise SystemExit("--day 또는 --control이 필요하다")
    src = INPUT_DIR / "complaints" / f"{args.day}.jsonl"
    if not src.exists():
        raise SystemExit(f"입력 파일 없음: {src}")

    lines = [l for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    sent = 0
    for i, line in enumerate(lines):
        producer.send(TOPIC, line.encode("utf-8"))
        sent += 1
        # 오염 이벤트는 이벤트 사이(10번째 뒤)에 끼워 넣는다 — 경계가 아니라 한복판에서
        # 파이프라인이 멈추지 않음을 봐야 격리의 증거가 된다
        if args.poison and i == 9:
            for _ in range(args.poison):
                producer.send(TOPIC, POISON_PAYLOAD)
    resent = 0
    if args.resend_last:
        # 전송 확인(ack)을 못 받은 생산자가 마지막 배치를 다시 보내는 상황의 재현(4장)
        for line in lines[-args.resend_last:]:
            producer.send(TOPIC, line.encode("utf-8"))
            resent += 1
    producer.flush()
    print(f"[ingester] {args.day}: 발행 {sent}건"
          + (f" + 재전송 {resent}건" if resent else "")
          + (f" + 오염 {args.poison}건" if args.poison else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
