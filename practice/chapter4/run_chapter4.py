#!/usr/bin/env python3
"""Chapter 4: Kafka Producer/Consumer 실습 오케스트레이터.

세 가지 전달 시나리오를 실제 브로커에서 실행하고,
"메시지 유실·중복·지연 관찰 보고서"(ch4_delivery_report.json)를 산출한다.

  A. baseline        : 정상 전송·소비 — 유실 0, 중복 0, 지연 측정
  B. at-most-once    : 커밋 먼저 + 처리 중 크래시 → 유실 관찰
  C. at-least-once   : 처리 먼저 + 커밋 전 크래시 → 중복 관찰

선수 조건: 3장 최소 구성의 브로커 기동
    cd ../chapter3 && docker compose up -d zookeeper kafka

실행:
    python run_chapter4.py
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError, UnknownTopicOrPartitionError

BASE_DIR = Path(__file__).resolve().parent
CODE_DIR = BASE_DIR / "code"
OUTPUT_DIR = BASE_DIR / "data" / "output"

BOOTSTRAP = "localhost:9092"
TOPIC = "public.complaint.received.v1"
PARTITIONS = 3
CRASH_EXIT_CODE = 42


def reset_topic(groups: tuple = ("g-baseline", "g-amo", "g-alo")) -> None:
    """토픽·컨슈머 그룹을 정리 후 3개 파티션으로 재생성한다(재실행 간 오염 방지).

    토픽 재생성만으로는 브로커에 남은 그룹 커밋 오프셋이 환경에 따라
    유지될 수 있어, 재실행 시 새 레코드를 건너뛰는 원인이 된다. 비활성
    그룹을 명시적으로 삭제해 항상 처음부터 읽게 만든다.
    """
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP, request_timeout_ms=15000)
    try:
        try:
            # 이전 실행이 남긴 그룹(커밋 오프셋 포함) 제거 — 그룹이 없으면
            # 응답의 에러 코드로 돌아올 뿐 예외가 아니므로 결과만 출력한다.
            result = admin.delete_groups(list(groups))
            print(f"[reset] consumer group 삭제: {result}")
        except Exception as exc:  # 브로커가 지원하지 않는 경우 등
            print(f"[reset] consumer group 삭제 건너뜀: {exc}")
        try:
            admin.delete_topics([TOPIC])
        except UnknownTopicOrPartitionError:
            pass
        # 삭제가 비동기이므로 목록에서 사라질 때까지 대기
        deadline = time.time() + 30
        while TOPIC in admin.list_topics() and time.time() < deadline:
            time.sleep(0.5)
        if TOPIC in admin.list_topics():
            # 삭제가 비활성화됐거나 지연되면 옛 토픽으로 다음 시나리오가
            # 오염되므로, 조용히 진행하지 않고 명시적으로 실패한다.
            raise RuntimeError(f"토픽 삭제가 완료되지 않음: {TOPIC} (delete.topic.enable 확인)")
        # 재생성(삭제 여파가 남아 있으면 잠시 재시도)
        created = False
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                admin.create_topics(
                    [NewTopic(name=TOPIC, num_partitions=PARTITIONS, replication_factor=1)]
                )
                created = True
                break
            except TopicAlreadyExistsError:
                time.sleep(1.0)
        deadline = time.time() + 15
        while TOPIC not in admin.list_topics() and time.time() < deadline:
            time.sleep(0.5)
        if not created or TOPIC not in admin.list_topics():
            raise RuntimeError(f"토픽 재생성 실패: {TOPIC}")
    finally:
        admin.close()


def run(script: str, *args: str, expect_codes: tuple = (0,)) -> int:
    """실습 스크립트를 서브프로세스로 실행한다."""
    cmd = [sys.executable, str(CODE_DIR / script), *args]
    print(f"\n$ {' '.join(cmd[1:])}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode not in expect_codes:
        raise RuntimeError(f"{script} 종료 코드 {result.returncode} (예상: {expect_codes})")
    return result.returncode


def analyze_store(group: str, scenario: str) -> dict:
    """처리 기록(JSONL)에서 유실·중복 계산의 재료를 뽑는다."""
    store = OUTPUT_DIR / f"ch4_processed_{group}.jsonl"
    ids: list[str] = []
    if store.exists():
        for line in store.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("scenario") == scenario:
                ids.append(rec["event_id"])
    counts = Counter(ids)
    return {
        "processed_records": len(ids),
        "unique_events": len(counts),
        "duplicated_events": sum(1 for c in counts.values() if c > 1),
        "duplicate_records": len(ids) - len(counts),
    }


def clear_store(group: str) -> None:
    store = OUTPUT_DIR / f"ch4_processed_{group}.jsonl"
    if store.exists():
        store.unlink()


def load_json(name: str) -> dict:
    return json.loads((OUTPUT_DIR / name).read_text(encoding="utf-8"))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "bootstrap": BOOTSTRAP,
        "topic": TOPIC,
        "partitions": PARTITIONS,
        "scenarios": {},
    }

    # ── 시나리오 A: 정상 전송(baseline) ─────────────────────────────
    # 컨슈머를 먼저 띄워 두고(동시 소비) 생산한다 — 지연(latency)이
    # "생산→소비" 실제 간격이 되도록. 컨슈머를 나중에 시작하면 지연은
    # 브로커가 아니라 "소비 시작 시점"이 지배한다(본문 관찰 포인트).
    print("=" * 60, "\n[A] baseline: 정상 전송·동시 소비\n", "=" * 60)
    reset_topic()
    clear_store("g-baseline")
    consumer_proc = subprocess.Popen(
        [sys.executable, str(CODE_DIR / "4-2-kafka-consumer.py"),
         "--group", "g-baseline", "--mode", "at-least-once", "--idle-sec", "15"],
        cwd=BASE_DIR,
    )
    time.sleep(8)  # 그룹 조인·파티션 할당 대기
    run("4-1-kafka-producer.py", "--count", "200", "--scenario", "baseline")
    if consumer_proc.wait(timeout=120) != 0:
        raise RuntimeError("baseline consumer 비정상 종료")
    produce = load_json("ch4_produce_baseline.json")
    consume = load_json("ch4_consume_g-baseline.json")
    stats = analyze_store("g-baseline", "baseline")
    report["scenarios"]["A_baseline"] = {
        "produced": produce["sent"],
        "partition_distribution": produce["partition_distribution"],
        "key_to_single_partition": produce["key_to_single_partition"],
        **stats,
        "lost_events": produce["sent"] - stats["unique_events"],
        "latency_ms": consume["latency_ms"],
    }

    # ── 시나리오 B: at-most-once + 처리 중 크래시 → 유실 ───────────
    print("=" * 60, "\n[B] at-most-once: 커밋 먼저 → 처리 중 크래시 → 유실\n", "=" * 60)
    reset_topic()
    clear_store("g-amo")
    run("4-1-kafka-producer.py", "--count", "30", "--scenario", "amo")
    code = run("4-2-kafka-consumer.py", "--group", "g-amo", "--mode", "at-most-once",
               "--crash-after", "10", expect_codes=(CRASH_EXIT_CODE,))
    # 크래시한 멤버는 그룹 탈퇴 신호 없이 죽는다 → 브로커가 세션 타임아웃
    # (10초) 후에야 제외한다. 그 전에 재시작하면 파티션 할당이 늦어지므로 대기.
    time.sleep(12)
    run("4-2-kafka-consumer.py", "--group", "g-amo", "--mode", "at-most-once",
        "--idle-sec", "15")  # 재시작
    stats = analyze_store("g-amo", "amo")
    report["scenarios"]["B_at_most_once_crash"] = {
        "produced": 30,
        "crash_after": 10,
        "crash_exit_code": code,
        **stats,
        "lost_events": 30 - stats["unique_events"],
    }

    # ── 시나리오 C: at-least-once + 커밋 전 크래시 → 중복 ──────────
    print("=" * 60, "\n[C] at-least-once: 처리 먼저 → 커밋 전 크래시 → 중복\n", "=" * 60)
    reset_topic()
    clear_store("g-alo")
    run("4-1-kafka-producer.py", "--count", "30", "--scenario", "alo")
    code = run("4-2-kafka-consumer.py", "--group", "g-alo", "--mode", "at-least-once",
               "--crash-after", "10", expect_codes=(CRASH_EXIT_CODE,))
    time.sleep(12)  # 세션 타임아웃(10초) 경과 대기 — 시나리오 B와 동일한 이유
    run("4-2-kafka-consumer.py", "--group", "g-alo", "--mode", "at-least-once",
        "--idle-sec", "15")  # 재시작
    stats = analyze_store("g-alo", "alo")
    report["scenarios"]["C_at_least_once_crash"] = {
        "produced": 30,
        "crash_after": 10,
        "crash_exit_code": code,
        **stats,
        "lost_events": 30 - stats["unique_events"],
    }

    out = OUTPUT_DIR / "ch4_delivery_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n" + "=" * 60)
    print(json.dumps(report["scenarios"], ensure_ascii=False, indent=2))
    print(f"\n[관찰 보고서 저장] {out}")


if __name__ == "__main__":
    main()
