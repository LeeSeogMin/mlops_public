#!/usr/bin/env python3
"""실습 13.1 피처 카탈로그와 접근 로그 구현.

7주차 산출물(registry에서 추출한 피처 정의 + 6주차 일별 확정 집계)을 입력으로,
피처 거버넌스의 네 장치를 SQLite와 표준 라이브러리만으로 독립 구현한다.

  13.2 피처 카탈로그   : 정의·소유자·목적·원천·개인정보·소비자·버전을 SQLite에 적재
  13.3 접근 제어·이력  : 역할 기반 정책(RBAC)으로 허용/거부를 판정하고 access_log에 적재
  13.4 품질 점검       : 결측·범위·유일성 규칙을 7주차 실데이터 9행에 적용
  13.4 변경 관리       : day_unmapped_rate 산식 v1→v2의 값 변화·영향 소비자·승인 기록
        + 감사 점검표  : access_log·카탈로그·품질·변경 이력에서 자동 생성

원칙
  - 모든 값은 8·6주차 실측 입력에서 유도한다(손으로 지어낸 카탈로그 금지).
  - 타임스탬프는 입력 데이터에서 유도한다(now() 금지) → 증거 JSON 재실행 바이트 동일.
  - SQLite(.sqlite)는 빌드 산출물(gitignore), 커밋 증거는 JSON뿐.

실행: cd practice/chapter12 && venv/bin/python run_chapter12.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc

# 지역 코드 → 이름(7.2 행정표준코드) — 카탈로그·품질 판정의 표시용
REGION_NAME = {"11440": "마포구", "11620": "관악구", "11680": "강남구"}

# 피처별 소비자 — 저장소에 문서화된 사실(장 간 연결)에서만 구성한다.
#   complaint_count : 9장 훈련 쌍의 입력, 10장 champion 서빙 입력, 13주차 통합 MVP 소비
#   day_unmapped_rate: complaint_model_v1 서비스에 등록된 품질 피처(9장 훈련 서비스)
FEATURE_CONSUMERS = {
    "complaint_count": ["complaint_model_v1 훈련(9장)", "champion 서빙(10장)", "통합 MVP(13주차)"],
    "day_unmapped_rate": ["complaint_model_v1 서비스(9장 훈련)"],
}

# 접근 정책: 역할 → 허용 행위 집합. 등록되지 않은 역할은 전부 거부.
#   read_definition: 카탈로그 메타(정의·소유자 등) 열람
#   read_value     : 원시 피처 값 조회
#   read_log       : 접근 사용 이력(감사 로그) 열람
ACCESS_POLICY = {
    "training_pipeline": {"read_definition", "read_value"},   # 9장 훈련
    "serving_api": {"read_definition", "read_value"},         # 10장 서빙
    "analyst": {"read_definition", "read_value"},             # 분석가(공개 집계)
    "external_auditor": {"read_definition", "read_log"},      # 외부감사 — 값 조회 불가(목적 제한)
}

# 접근 요청 시퀀스(결정적) — (역할, 피처, 행위, 목적).
# 허용/거부가 골고루 나오도록 구성하며, 거부 사유는 정책·카탈로그에서 도출된다.
ACCESS_REQUESTS = [
    ("training_pipeline", "complaint_count", "read_value", "일별 예측 모델 훈련"),
    ("training_pipeline", "day_unmapped_rate", "read_value", "훈련 데이터 품질 피처"),
    ("serving_api", "complaint_count", "read_value", "champion 온라인 예측"),
    ("serving_api", "complaint_count", "read_definition", "서빙 입력 스키마 확인"),
    ("analyst", "complaint_count", "read_definition", "지역별 민원 추이 분석"),
    ("analyst", "complaint_count", "read_value", "월간 민원 리포트"),
    ("analyst", "complaint_count", "read_log", "동료 조회 이력 확인"),        # 거부: 로그 열람 권한 없음
    ("external_auditor", "day_unmapped_rate", "read_definition", "정의서 감사"),
    ("external_auditor", "complaint_count", "read_log", "접근 이력 감사"),
    ("external_auditor", "complaint_count", "read_value", "원시 값 확인 시도"),  # 거부: 감사 역할 값 조회 제한
    ("marketing_bot", "complaint_count", "read_value", "미등록 역할 조회"),      # 거부: 미등록 역할
    ("analyst", "resident_arrears", "read_value", "가구 단위 민감 피처 조회"),   # 거부: 카탈로그 미등록
]


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def load_inputs(input_dir: Path) -> tuple[dict, list[dict], list[dict]]:
    """7주차 정의 JSON + 6주차 일별 집계 3일치를 읽어 피처 정의와 원천 9행을 만든다."""
    definitions = json.loads((input_dir / "ch7_feature_definitions.json").read_text("utf-8"))

    days = sorted(p.name for p in (input_dir / "ch6_daily").iterdir() if p.is_dir())
    feature_rows: list[dict] = []
    quality_by_day: list[dict] = []
    for day in days:
        daily = json.loads((input_dir / "ch6_daily" / day / "daily_summary.json").read_text("utf-8"))
        quality = json.loads((input_dir / "ch6_daily" / day / "quality_check.json").read_text("utf-8"))
        # event_timestamp = 값이 확정·공개된 시점 = 집계 대상일 다음 날 00:00 UTC (8.3 규약)
        as_of = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
        quality_by_day.append({
            "date": day, "event_timestamp": _iso(as_of),
            "unmapped": quality["unmapped"], "valid": quality["valid"],
            "physical": quality["physical"], "dup_removed": quality["dup_removed"],
            "recorded_unmapped_rate": quality["unmapped_rate"],
        })
        for region in daily["by_region"]:
            feature_rows.append({
                "lawd_cd": region["lawd_cd"],
                "region": region["region"],
                "event_timestamp": _iso(as_of),
                "aggregate_date": day,
                "complaint_count": region["count"],
                "day_unmapped_rate": quality["unmapped_rate"],  # 7주차 기록값(v1)
            })
    return definitions, feature_rows, quality_by_day


def build_catalog(conn: sqlite3.Connection, definitions: dict) -> list[dict]:
    """7주차 정의에서 카탈로그 행을 생성해 SQLite에 적재한다(정의를 손으로 짓지 않는다)."""
    gov = definitions["feature_view"]["governance"]
    conn.execute("""
        CREATE TABLE feature_catalog(
            feature_name TEXT PRIMARY KEY, dtype TEXT, definition TEXT,
            owner TEXT, purpose TEXT, source TEXT, privacy TEXT,
            consumers TEXT, timestamp_semantics TEXT, ttl_days INTEGER, version TEXT)
    """)
    catalog: list[dict] = []
    for feat in definitions["feature_view"]["features"]:
        name = feat["name"]
        row = {
            "feature_name": name,
            "dtype": feat["dtype"],
            "definition": feat["description"],
            "owner": gov["owner"],
            "purpose": "민원 급증 예측(complaint_model_v1)",
            "source": gov["source"],
            "privacy": gov["privacy"],
            "consumers": FEATURE_CONSUMERS[name],
            "timestamp_semantics": definitions["feature_view"]["timestamp_semantics"],
            "ttl_days": definitions["feature_view"]["ttl_days"],
            "version": definitions["feature_service"]["name"],
        }
        conn.execute(
            "INSERT INTO feature_catalog VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (row["feature_name"], row["dtype"], row["definition"], row["owner"],
             row["purpose"], row["source"], row["privacy"],
             json.dumps(row["consumers"], ensure_ascii=False),
             row["timestamp_semantics"], row["ttl_days"], row["version"]))
        catalog.append(row)
    conn.commit()
    return catalog


def evaluate_access(conn: sqlite3.Connection, catalog_names: set[str],
                    base_time: datetime) -> dict:
    """접근 요청 시퀀스를 정책으로 판정하고 access_log에 적재한다."""
    conn.execute("""
        CREATE TABLE access_log(
            seq INTEGER PRIMARY KEY, ts TEXT, role TEXT, feature TEXT,
            action TEXT, purpose TEXT, decision TEXT, reason TEXT)
    """)
    log: list[dict] = []
    for i, (role, feature, action, purpose) in enumerate(ACCESS_REQUESTS):
        ts = _iso(base_time + timedelta(minutes=i))  # 결정적 타임스탬프(요청 순번)
        if role not in ACCESS_POLICY:
            decision, reason = "DENY", "미등록 역할 — 정책에 없음"
        elif feature not in catalog_names:
            decision, reason = "DENY", "카탈로그 미등록 피처 — 접근의 전제는 등록"
        elif action not in ACCESS_POLICY[role]:
            if action == "read_value" and role == "external_auditor":
                reason = "감사 역할은 원시 값 조회 불가 — 메타데이터·로그만(목적 제한)"
            elif action == "read_log":
                reason = "로그 열람은 감사 권한 필요"
            else:
                reason = f"{role} 역할에 {action} 권한 없음"
            decision = "DENY"
        else:
            decision, reason = "ALLOW", "정책 허용"
        conn.execute("INSERT INTO access_log VALUES(?,?,?,?,?,?,?,?)",
                     (i, ts, role, feature, action, purpose, decision, reason))
        log.append({"seq": i, "ts": ts, "role": role, "feature": feature,
                    "action": action, "purpose": purpose,
                    "decision": decision, "reason": reason})
    conn.commit()
    allow = sum(1 for r in log if r["decision"] == "ALLOW")
    deny = sum(1 for r in log if r["decision"] == "DENY")
    return {"requests": len(log), "allow": allow, "deny": deny, "log": log}


def check_quality(feature_rows: list[dict]) -> dict:
    """피처 단위 품질 규칙 3종을 7주차 실데이터 9행에 적용(11장 분포 감시와 다른 층)."""
    n = len(feature_rows)
    # 완전성(completeness): 값 결측 없음 — 공공 3대 품질지표의 '완전성'
    complete = sum(1 for r in feature_rows
                   if r["complaint_count"] is not None and r["day_unmapped_rate"] is not None)
    # 정확성(accuracy/range): 값이 유효 범위 내 — 건수 ≥ 0, 실패율 ∈ [0,1]
    in_range = sum(1 for r in feature_rows
                   if r["complaint_count"] >= 0 and 0.0 <= r["day_unmapped_rate"] <= 1.0)
    # 일관성(uniqueness): (lawd_cd, event_timestamp)가 유일 — 중복 키 없음
    keys = [(r["lawd_cd"], r["event_timestamp"]) for r in feature_rows]
    unique = len(set(keys))
    rules = [
        {"rule": "완전성(결측 없음)", "quality_dim": "완전성", "passed": complete == n,
         "detail": f"non-null {complete}/{n}"},
        {"rule": "정확성(범위: count≥0, rate∈[0,1])", "quality_dim": "정확성", "passed": in_range == n,
         "detail": f"in-range {in_range}/{n}"},
        {"rule": "일관성(키 유일성)", "quality_dim": "일관성", "passed": unique == n,
         "detail": f"unique-keys {unique}/{n}"},
    ]
    return {"rows": n, "rules": rules, "all_passed": all(r["passed"] for r in rules)}


def manage_change(conn: sqlite3.Connection, quality_by_day: list[dict],
                  catalog: list[dict], feature_rows: list[dict],
                  base_time: datetime) -> dict:
    """day_unmapped_rate 산식 변경 v1(÷valid)→v2(÷physical)의 영향을 실측한다."""
    conn.execute("""
        CREATE TABLE change_log(
            change_id TEXT PRIMARY KEY, ts TEXT, feature TEXT,
            from_def TEXT, to_def TEXT, requester TEXT, approver TEXT,
            reason TEXT, impacted_consumers TEXT, changed_rows INTEGER)
    """)
    per_day = []
    changed_days = 0
    for q in quality_by_day:
        v1 = round(q["unmapped"] / q["valid"], 4)       # 현행 정의: 미매핑 / 유효건수
        v2 = round(q["unmapped"] / q["physical"], 4)    # 제안 정의: 미매핑 / 물리건수
        changed = v1 != v2
        changed_days += int(changed)
        per_day.append({"date": q["date"], "event_timestamp": q["event_timestamp"],
                        "unmapped": q["unmapped"], "valid": q["valid"],
                        "physical": q["physical"], "v1_rate": v1, "v2_rate": v2,
                        "changed": changed})
    # 영향 행 = 값이 바뀌는 날에 속한 실제 피처 행 수(지역 수 하드코딩 대신 직접 집계)
    changed_dates = {d["date"] for d in per_day if d["changed"]}
    changed_rows = sum(1 for r in feature_rows if r["aggregate_date"] in changed_dates)
    impacted = next(c["consumers"] for c in catalog if c["feature_name"] == "day_unmapped_rate")
    change = {
        "change_id": "CHG-2026-07-day_unmapped_rate-v2",
        "ts": _iso(base_time + timedelta(hours=1)),
        "feature": "day_unmapped_rate",
        "from_def": "미매핑 건수 / 유효 건수(valid)",
        "to_def": "미매핑 건수 / 물리 건수(physical)",
        "requester": "품질관리팀(가상)",
        "approver": "민원데이터팀 소유자(가상)",
        "reason": "물리 수집량 대비 실패율로 정의 통일 — 중복 포함 원자료 기준",
        "impacted_consumers": impacted,
        "changed_days": changed_days,
        "changed_rows": changed_rows,
        "per_day": per_day,
    }
    conn.execute("INSERT INTO change_log VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (change["change_id"], change["ts"], change["feature"],
                  change["from_def"], change["to_def"], change["requester"],
                  change["approver"], change["reason"],
                  json.dumps(impacted, ensure_ascii=False), changed_rows))
    conn.commit()
    return change


def build_audit_checklist(catalog: list[dict], access: dict,
                          quality: dict, change: dict) -> dict:
    """access_log·카탈로그·품질·변경 이력에서 감사 점검표를 자동 생성한다(13주차 선례)."""
    log = access["log"]
    value_reads = [r for r in log if r["action"] == "read_value"]
    allowed_value_reads = [r for r in value_reads if r["decision"] == "ALLOW"]
    unregistered_reqs = [r for r in log if r["role"] not in ACCESS_POLICY]
    auditor_value_allows = [r for r in log if r["role"] == "external_auditor"
                            and r["action"] == "read_value" and r["decision"] == "ALLOW"]
    denies = [r for r in log if r["decision"] == "DENY"]

    items = [
        ("모든 접근 요청이 로그에 기록되었는가",
         len(log) == len(ACCESS_REQUESTS)),
        ("거부된 요청이 전부 사유를 보유하는가",
         all(r["reason"] for r in denies)),
        ("허용된 원시 값 조회가 전부 인가된 역할인가",
         all(r["role"] in ACCESS_POLICY and "read_value" in ACCESS_POLICY[r["role"]]
             for r in allowed_value_reads)),
        ("미등록 역할의 접근이 전부 거부되었는가",
         all(r["decision"] == "DENY" for r in unregistered_reqs)),
        ("감사 역할의 원시 값 조회가 0건인가(목적 제한)",
         len(auditor_value_allows) == 0),
        ("카탈로그의 모든 피처가 소유자·개인정보 등급·소비자를 보유하는가",
         all(c["owner"] and c["privacy"] and c["consumers"] for c in catalog)),
        ("개인정보 등급이 비어 있는 피처가 0건인가",
         all(c["privacy"] for c in catalog)),
        ("품질 규칙(완전성·정확성·일관성) 3종이 전부 통과했는가",
         quality["all_passed"]),
        ("변경 이력에 요청자·승인자·사유가 기록되었는가",
         bool(change["requester"] and change["approver"] and change["reason"])),
        ("정의 변경이 영향 소비자를 식별했는가",
         len(change["impacted_consumers"]) > 0),
    ]
    checklist = [{"no": i + 1, "item": item, "passed": bool(ok)}
                 for i, (item, ok) in enumerate(items)]
    passed = sum(1 for c in checklist if c["passed"])
    return {"total": len(checklist), "passed": passed,
            "all_passed": passed == len(checklist), "items": checklist}


def build_governance(input_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    definitions, feature_rows, quality_by_day = load_inputs(input_dir)

    # 접근/변경 타임스탬프의 기준 = 마지막 피처 확정 시점(입력에서 유도, now() 금지)
    base_time = max(datetime.strptime(r["event_timestamp"], "%Y-%m-%dT%H:%M:%S+00:00")
                    .replace(tzinfo=UTC) for r in feature_rows)

    db_path = output_dir / "feature_governance.sqlite"
    if db_path.exists():
        db_path.unlink()  # 재실행 결정성 — 매번 새로 구축
    conn = sqlite3.connect(db_path)
    try:
        catalog = build_catalog(conn, definitions)
        catalog_names = {c["feature_name"] for c in catalog}
        access = evaluate_access(conn, catalog_names, base_time)
        quality = check_quality(feature_rows)
        change = manage_change(conn, quality_by_day, catalog, feature_rows, base_time)
        audit = build_audit_checklist(catalog, access, quality, change)
    finally:
        conn.close()

    report = {
        "practice": "13.1 피처 카탈로그와 접근 로그",
        "inputs": {
            "feature_definition_source": "ch7_feature_definitions.json(7주차 registry 추출)",
            "feature_rows": len(feature_rows),
            "days": [q["date"] for q in quality_by_day],
        },
        "catalog": {"features": len(catalog), "entries": catalog},
        "access_control": {
            "roles": sorted(ACCESS_POLICY.keys()),
            "requests": access["requests"], "allow": access["allow"],
            "deny": access["deny"], "log": access["log"],
        },
        "quality": quality,
        "change_management": change,
        "audit_checklist": audit,
    }

    (output_dir / "ch12_governance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")
    (output_dir / "ch12_governance_checklist.json").write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_governance(Path(args.input), Path(args.output))
    a = report["access_control"]
    print(f"카탈로그 피처 {report['catalog']['features']}개, "
          f"접근 요청 {a['requests']}건(허용 {a['allow']}/거부 {a['deny']}), "
          f"품질 {report['quality']['rows']}행, "
          f"감사 점검 {report['audit_checklist']['passed']}/{report['audit_checklist']['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
