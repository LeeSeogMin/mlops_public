#!/usr/bin/env python3
"""4-1: 민원 이벤트 Kafka Producer.

가상의 민원 접수 이벤트를 생성해 Kafka 토픽으로 전송한다.

주의(정직성): 민원 이벤트 자체는 시뮬레이션 데이터다(개인정보가 있는 실제
민원을 쓸 수 없기 때문). 이 실습의 관찰 대상은 "데이터 내용"이 아니라
"실제 브로커의 전달 동작"(파티션 배치·오프셋·유실·중복·지연)이며,
본문에 인용하는 수치는 전부 실제 실행 로그에서 나온다.

실행 예:
    python code/4-1-kafka-producer.py --count 200 --scenario baseline
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "output"

DEFAULT_TOPIC = "public.complaint.received.v1"
DEFAULT_BOOTSTRAP = "localhost:9092"

# 파티션 키로 쓰는 지역구(순서 보장 단위). 일부만 사용해 키 분포를 관찰한다.
DISTRICTS = ["종로구", "중구", "용산구", "성동구", "강남구", "송파구", "마포구", "관악구"]
CATEGORIES = ["불법주차", "도로파손", "소음", "쓰레기", "가로등고장"]


def ensure_topic(bootstrap: str, topic: str, partitions: int) -> None:
    """토픽이 없으면 지정 파티션 수로 생성한다(있으면 그대로 둔다)."""
    admin = KafkaAdminClient(bootstrap_servers=bootstrap, request_timeout_ms=15000)
    try:
        admin.create_topics(
            [NewTopic(name=topic, num_partitions=partitions, replication_factor=1)]
        )
        # 생성 직후 메타데이터 전파를 잠시 기다린다.
        time.sleep(1.0)
    except TopicAlreadyExistsError:
        pass
    finally:
        admin.close()


def make_event(seq: int, scenario: str, rng: random.Random) -> dict:
    """민원 접수 이벤트 1건을 생성한다(시뮬레이션 입력)."""
    return {
        "event_id": f"{scenario}-{seq:06d}",
        "scenario": scenario,
        "district": rng.choice(DISTRICTS),
        "category": rng.choice(CATEGORIES),
        "event_time": datetime.now(timezone.utc).isoformat(),
        "send_ts": time.time(),  # 소비 측 지연(latency) 측정용
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="민원 이벤트 Producer")
    parser.add_argument("--bootstrap", default=DEFAULT_BOOTSTRAP)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--partitions", type=int, default=3)
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ensure_topic(args.bootstrap, args.topic, args.partitions)

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap,
        # 안전한 기본값: 동기화된 복제본 전체의 기록 확인을 기다린다.
        acks="all",
        key_serializer=lambda k: k.encode("utf-8"),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )

    rng = random.Random(args.seed)
    partition_counter: Counter = Counter()
    district_partition: dict[str, set] = {}
    started = time.time()

    for seq in range(1, args.count + 1):
        event = make_event(seq, args.scenario, rng)
        # 같은 키(지역구)는 같은 파티션으로 간다 → 지역구 단위 순서 보장.
        future = producer.send(args.topic, key=event["district"], value=event)
        meta = future.get(timeout=15)  # 전송 확인(브로커의 ack)을 기다린다
        partition_counter[meta.partition] += 1
        district_partition.setdefault(event["district"], set()).add(meta.partition)

    producer.flush()
    producer.close()
    elapsed = round(time.time() - started, 3)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": args.topic,
        "scenario": args.scenario,
        "acks": "all",
        "sent": args.count,
        "elapsed_sec": elapsed,
        "partition_distribution": {str(p): c for p, c in sorted(partition_counter.items())},
        # 지역구별로 배정된 파티션 집합 — 전부 크기 1이면 "같은 키→같은 파티션" 확인
        "district_to_partitions": {d: sorted(ps) for d, ps in sorted(district_partition.items())},
        "key_to_single_partition": all(len(ps) == 1 for ps in district_partition.values()),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"ch4_produce_{args.scenario}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[저장] {out_path}")


if __name__ == "__main__":
    main()
