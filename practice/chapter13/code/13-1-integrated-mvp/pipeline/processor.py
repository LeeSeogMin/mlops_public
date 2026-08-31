#!/usr/bin/env python3
"""13주차 통합 MVP: processor — 소비·정제·멱등 반영·일 마감 집계·예측 호출.

앞 장 부품의 재조립이다(새 규칙 없음):
- 정제 4갈래(공백 보정·약칭 보정·표준코드 매핑·미기재/미매핑 분리 보고): 6주차 규약
- 멱등 반영(complaint_id UPSERT — 재전송·중복 접수를 업무 상태 변경 없이 흡수): 4주차 규약
- 일 마감(_SUCCESS 마커는 마지막에, 마커 있으면 재마감 안 함): 6주차 규약
- 예측(모델 API 호출 — champion 고정 이미지): 9·10장 규약
- 지연 레이블(익일 실제 건수 도착 시 전날 예측의 절대 오차 기록): 11장 규약

파싱 불가 페이로드는 격리 큐(quarantine)로 빠지고 파이프라인은 계속 간다(14.5 드릴 D1).
모델 API 실패 시 집계는 확정하고 예측만 pending_retry로 남긴다(부분 실패 격리 — 드릴 D3).

실행(컨테이너): compose 서비스 processor로 상시 실행. 상태는 /data/out에 남는다.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from kafka import KafkaConsumer

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:29092")
TOPIC = os.environ.get("TOPIC", "complaints.raw")
MODEL_API = os.environ.get("MODEL_API", "http://model-api:8000")
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/in"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "/data/out"))

ALIASES = {"강남": "강남구", "마포": "마포구", "관악": "관악구"}  # 7장 약칭 보정 사전


def load_mapping() -> dict[str, str]:
    with open(INPUT_DIR / "lawd_cd_seoul.csv", encoding="utf-8") as f:
        return {row["region_std"]: row["lawd_cd"] for row in csv.DictReader(f)}


def dump_json(path: Path, obj) -> None:
    """결정적 직렬화(키 정렬·고정 포맷) — 재실행 산출물 비교의 전제(6주차 규약)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS complaints (
      complaint_id TEXT PRIMARY KEY,
      day TEXT, region_raw TEXT, category TEXT, created_at TEXT,
      region_std TEXT, lawd_cd TEXT,
      status TEXT,                 -- mapped | missing | unmapped
      ws_stripped INTEGER, alias_fixed INTEGER,
      seen_count INTEGER
    );
    CREATE TABLE IF NOT EXISTS received_log (day TEXT PRIMARY KEY, n INTEGER);
    CREATE TABLE IF NOT EXISTS predictions (
      target_date TEXT, lawd_cd TEXT, region TEXT,
      x_prev_count INTEGER, forecast REAL,
      model_name TEXT, model_version TEXT, model_source TEXT,
      status TEXT, attempts INTEGER, error TEXT,
      actual INTEGER, abs_error REAL,
      PRIMARY KEY (target_date, lawd_cd)
    );
    CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, n INTEGER);
    """)
    return db


def bump(db: sqlite3.Connection, name: str, by: int = 1) -> None:
    db.execute("INSERT INTO counters(name, n) VALUES(?, ?) "
               "ON CONFLICT(name) DO UPDATE SET n = n + ?", (name, by, by))


def quarantine(raw: bytes, reason: str) -> None:
    """오염 이벤트 격리 — 버리지 않고 원문 보존(사후 분석·재처리 가능성)."""
    qdir = OUT_DIR / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    with (qdir / "quarantine.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"reason": reason,
                            "payload": raw.decode("utf-8", errors="replace")},
                           ensure_ascii=False, sort_keys=True) + "\n")


def ingest_complaint(db: sqlite3.Connection, rec: dict, mapping: dict[str, str]) -> None:
    """정제(7장) 후 멱등 반영(5장). 재수신은 seen_count만 올린다 — 업무 상태 불변."""
    day = rec["created_at"][:10]
    db.execute("INSERT INTO received_log(day, n) VALUES(?, 1) "
               "ON CONFLICT(day) DO UPDATE SET n = n + 1", (day,))

    raw = rec.get("region_raw")
    name = (raw or "").strip()
    ws = 1 if (raw is not None and name != raw) else 0
    alias = 1 if name in ALIASES else 0
    name = ALIASES.get(name, name)
    if not name:
        status, region_std, lawd = "missing", None, None
    elif name in mapping:
        status, region_std, lawd = "mapped", name, mapping[name]
    else:
        status, region_std, lawd = "unmapped", None, None

    # 4주차 UPSERT: 같은 complaint_id의 재수신(수송 재전송이든 중복 접수든)은
    # 업무 상태를 바꾸지 않고 관찰 횟수만 남긴다 — 멱등의 실체
    db.execute("""
      INSERT INTO complaints(complaint_id, day, region_raw, category, created_at,
                             region_std, lawd_cd, status, ws_stripped, alias_fixed, seen_count)
      VALUES(?,?,?,?,?,?,?,?,?,?,1)
      ON CONFLICT(complaint_id) DO UPDATE SET seen_count = seen_count + 1
    """, (rec["complaint_id"], day, raw, rec.get("category"), rec["created_at"],
          region_std, lawd, status, ws, alias))
    db.commit()


def call_predict(lawd_cd: str, x_prev: int) -> tuple[dict | None, str | None, float]:
    """모델 API 호출. (응답, 정규화된 오류 코드, 지연 ms)를 돌려준다."""
    body = json.dumps({"lawd_cd": lawd_cd, "x_prev_count": x_prev}).encode("utf-8")
    req = urllib.request.Request(f"{MODEL_API}/predict", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data, None, (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}", (time.monotonic() - t0) * 1000
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        # 오류 문자열은 환경마다 달라 증거를 오염시킨다 — 코드로 정규화(휘발성 배제)
        return None, "api_unreachable", (time.monotonic() - t0) * 1000


def day_counts(db: sqlite3.Connection, date: str) -> list[dict]:
    rows = db.execute("""
      SELECT lawd_cd, region_std, COUNT(*) FROM complaints
      WHERE day = ? AND status = 'mapped' GROUP BY lawd_cd, region_std ORDER BY lawd_cd
    """, (date,)).fetchall()
    return [{"lawd_cd": cd, "region": rg, "count": n} for cd, rg, n in rows]


def write_quality(db: sqlite3.Connection, date: str, out: Path) -> dict:
    physical = (db.execute("SELECT n FROM received_log WHERE day=?", (date,)).fetchone() or [0])[0]
    q = {"date": date, "physical_received": physical}
    row = db.execute("""
      SELECT COUNT(*),
             SUM(status='mapped'), SUM(status='missing'), SUM(status='unmapped'),
             SUM(ws_stripped), SUM(alias_fixed), SUM(seen_count) - COUNT(*)
      FROM complaints WHERE day = ?
    """, (date,)).fetchone()
    unique, mapped, missing, unmapped, ws, alias, redelivered = [int(x or 0) for x in row]
    q.update(unique=unique, dedup_dropped=redelivered, mapped=mapped, missing=missing,
             unmapped=unmapped, ws_stripped=ws, alias_fixed=alias,
             preservation_ok=(physical == unique + redelivered
                              and unique == mapped + missing + unmapped))
    dump_json(out / "quality.json", q)
    return q


def write_summary(db: sqlite3.Connection, date: str, out: Path) -> list[dict]:
    by_region = day_counts(db, date)
    cats = Counter(c for (c,) in db.execute(
        "SELECT category FROM complaints WHERE day=? AND status='mapped'", (date,)))
    summary = {
        "date": date,
        "by_region": by_region,
        "by_category": dict(sorted(cats.items())),
        "mapped_total": sum(r["count"] for r in by_region),
        "top_category": max(cats.items(), key=lambda kv: kv[1])[0] if cats else None,
    }
    dump_json(out / "daily_summary.json", summary)
    return by_region


def snapshot_predictions(db: sqlite3.Connection) -> None:
    rows = db.execute("""
      SELECT target_date, lawd_cd, region, x_prev_count, forecast,
             model_name, model_version, model_source, status, attempts, error,
             actual, abs_error
      FROM predictions ORDER BY target_date, lawd_cd
    """).fetchall()
    cols = ["target_date", "lawd_cd", "region", "x_prev_count", "forecast",
            "model_name", "model_version", "model_source", "status", "attempts",
            "error", "actual", "abs_error"]
    dump_json(OUT_DIR / "predictions_snapshot.json",
              [dict(zip(cols, r)) for r in rows])


def snapshot_counters(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT name, n FROM counters ORDER BY name").fetchall()
    dump_json(OUT_DIR / "ops_counters.json", dict(rows))


def next_date(date: str) -> str:
    import datetime
    d = datetime.date.fromisoformat(date)
    return (d + datetime.timedelta(days=1)).isoformat()


def close_day(db: sqlite3.Connection, date: str, mapping: dict[str, str]) -> None:
    out = OUT_DIR / "daily" / date
    if (out / "_SUCCESS").exists():
        print(f"[processor] {date}: 이미 마감됨(_SUCCESS 존재) — 재마감하지 않는다(멱등)")
        return

    q = write_quality(db, date, out)
    by_region = write_summary(db, date, out)
    print(f"[processor] {date} 마감: 물리수신 {q['physical_received']} / 고유 {q['unique']}"
          f" (중복 흡수 {q['dedup_dropped']}) → 매핑 {q['mapped']}"
          f" · 미기재 {q['missing']} · 미매핑 {q['unmapped']} · 보존 {q['preservation_ok']}")

    # 지연 레이블 도착(11장): 오늘 확정된 실제 건수로 어제의 예측을 채점한다
    labeled = 0
    for r in by_region:
        cur = db.execute("""
          UPDATE predictions SET actual = ?, abs_error = ABS(forecast - ?)
          WHERE target_date = ? AND lawd_cd = ? AND forecast IS NOT NULL
        """, (r["count"], r["count"], date, r["lawd_cd"]))
        labeled += cur.rowcount
    if labeled:
        maes = db.execute("SELECT ROUND(AVG(abs_error), 4) FROM predictions "
                          "WHERE target_date = ?", (date,)).fetchone()[0]
        print(f"[processor] {date}: 지연 레이블 도착 — 예측 {labeled}건 채점, 일 MAE {maes}")

    # 익일 예측(9·10장): 오늘 건수가 곧 내일 예측의 입력 피처(전일 건수 — 8장 의미론)
    target = next_date(date)
    for r in by_region:
        resp, err, ms = call_predict(r["lawd_cd"], r["count"])
        if resp is not None:
            db.execute("""
              INSERT OR REPLACE INTO predictions
                (target_date, lawd_cd, region, x_prev_count, forecast,
                 model_name, model_version, model_source, status, attempts, error)
              VALUES (?,?,?,?,?,?,?,?, 'ok', 1, NULL)
            """, (target, r["lawd_cd"], r["region"], r["count"], resp["forecast"],
                  resp["model_name"], resp["model_version"], resp["model_source"]))
            bump(db, "predict_ok")
            print(f"[processor] 예측 {target} {r['region']}: 입력 {r['count']}"
                  f" → {resp['forecast']} ({ms:.1f}ms)")
        else:
            # 부분 실패 격리: 집계 확정은 그대로 가고, 예측만 재시도 대기로 남긴다
            db.execute("""
              INSERT OR REPLACE INTO predictions
                (target_date, lawd_cd, region, x_prev_count, forecast,
                 model_name, model_version, model_source, status, attempts, error)
              VALUES (?,?,?,?, NULL, NULL, NULL, NULL, 'pending_retry', 1, ?)
            """, (target, r["lawd_cd"], r["region"], r["count"], err))
            bump(db, "predict_failed")
            print(f"[processor] 예측 {target} {r['region']}: 실패({err}) → pending_retry")
    db.commit()
    snapshot_predictions(db)
    snapshot_counters(db)

    # 마커는 마지막에 쓴다(6주차 규약) — 마커가 있으면 이 날의 집계는 확정본이다
    (out / "_SUCCESS").write_text("", encoding="utf-8")
    print(f"[processor] {date}: _SUCCESS 확정")


def retry_pending(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT target_date, lawd_cd, region, x_prev_count, attempts "
                      "FROM predictions WHERE status = 'pending_retry' "
                      "ORDER BY target_date, lawd_cd").fetchall()
    print(f"[processor] 재시도 대상 {len(rows)}건")
    for target, cd, region, x, attempts in rows:
        resp, err, ms = call_predict(cd, x)
        if resp is not None:
            db.execute("""
              UPDATE predictions SET forecast=?, model_name=?, model_version=?,
                model_source=?, status='ok', attempts=?, error=NULL
              WHERE target_date=? AND lawd_cd=?
            """, (resp["forecast"], resp["model_name"], resp["model_version"],
                  resp["model_source"], attempts + 1, target, cd))
            bump(db, "predict_ok")
            print(f"[processor] 재시도 성공 {target} {region}: 입력 {x}"
                  f" → {resp['forecast']} ({ms:.1f}ms, {attempts + 1}회째)")
        else:
            db.execute("UPDATE predictions SET attempts=?, error=? "
                       "WHERE target_date=? AND lawd_cd=?", (attempts + 1, err, target, cd))
            bump(db, "predict_failed")
            print(f"[processor] 재시도 실패 {target} {region}: {err}")
    db.commit()
    snapshot_predictions(db)
    snapshot_counters(db)


def ensure_topic() -> None:
    """토픽을 단일 파티션으로 멱등 생성한다(ingester와 동일 규약).

    브로커의 자동 생성을 꺼 두었으므로(compose 설정 — 단일 파티션 전제 보호),
    구독 시점에 토픽이 없으면 메타데이터 갱신 주기만큼 소비가 늦어질 수 있다.
    기동하는 쪽이 만들면 경합 자체가 사라진다.
    """
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError

    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    try:
        admin.create_topics([NewTopic(name=TOPIC, num_partitions=1, replication_factor=1)])
        print(f"[processor] 토픽 생성: {TOPIC} (partitions=1)")
    except TopicAlreadyExistsError:
        # 기존 토픽을 그냥 믿지 않는다 — 재사용 브로커에 다중 파티션 토픽이 남아
        # 있으면 마감(day_close) 순서 보장이 조용히 깨진다(ingester와 동일 검증)
        parts = KafkaConsumer(bootstrap_servers=BOOTSTRAP).partitions_for_topic(TOPIC)
        if parts != {0}:
            raise SystemExit(f"토픽 {TOPIC} 파티션이 단일이 아니다: {parts} — 마감 순서 보장 불가")
        print(f"[processor] 토픽 존재 확인: {TOPIC} (partitions=1)")
    finally:
        admin.close()


def main() -> None:
    mapping = load_mapping()
    db = init_db(OUT_DIR / "state" / "complaints.sqlite")
    print(f"[processor] 시작 — 토픽 {TOPIC}, 모델 API {MODEL_API}")
    ensure_topic()

    # 오프셋 자동 커밋 금지: 자동 커밋은 처리(내구 쓰기) 완료 전에 오프셋을 밀어
    # 올릴 수 있어, 크래시 시 그 메시지가 재생되지 않는다(유실 — at-most-once로
    # 강등). 처리 완료 후 수동 커밋이 at-least-once의 실체이며, 재생이 안전한
    # 이유는 멱등 설계(UPSERT·마커·키 쓰기)다 — 4·4주차 규약의 소비자판.
    consumer = KafkaConsumer(TOPIC, bootstrap_servers=BOOTSTRAP,
                             group_id="ch13-processor",
                             auto_offset_reset="earliest",
                             enable_auto_commit=False)
    for msg in consumer:
        try:
            rec = json.loads(msg.value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            quarantine(msg.value, "json_parse_error")
            bump(db, "quarantined")
            db.commit()
            snapshot_counters(db)
            print(f"[processor] 오염 이벤트 격리(json_parse_error) — 파이프라인은 계속")
            consumer.commit()
            continue

        if rec.get("type") == "day_close":
            close_day(db, rec["date"], mapping)
        elif rec.get("type") == "predict_retry":
            retry_pending(db)
        elif "complaint_id" in rec and "created_at" in rec:
            ingest_complaint(db, rec, mapping)
        else:
            quarantine(msg.value, "schema_violation")
            bump(db, "quarantined")
            db.commit()
            snapshot_counters(db)
            print(f"[processor] 스키마 위반 격리 — 파이프라인은 계속")
        # 내구 쓰기(SQLite·파일)가 끝난 뒤에만 오프셋을 커밋한다 — 여기서 크래시하면
        # 이 메시지는 재생되고, 멱등 설계가 재생을 무해하게 만든다
        consumer.commit()


if __name__ == "__main__":
    main()
