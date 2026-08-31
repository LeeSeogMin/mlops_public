#!/usr/bin/env python3
"""6주차 실습 7.1: 일별 민원 요약 DAG.

일별 민원 원천 파일(시뮬레이션 입력)을 검증→정제·표준코드 매핑→집계/품질 점검→보고서 작성
순서로 처리하는 Airflow DAG와, 일별 산출물을 주간으로 롤업하는 DAG를 정의한다.

- 입력 데이터는 시뮬레이션이다(개인정보가 있는 실제 민원을 쓸 수 없다).
  관찰 대상은 실제 Airflow 엔진의 의존성·실패 전파·재실행 동작이며,
  본문 인용 수치는 전부 실제 실행 산출물에서 나온다.
- 스케줄러 없이 dag.test()로 실행한다(Airflow 공식 디버깅 방식 — 단일 프로세스).
- 단독 실행: python code/6-1-daily-report-dag.py  (2026-07-01 하루치 실행)
  전체 시나리오: python run_chapter6.py
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"

# Airflow 환경을 실습 폴더 내부로 고정한다(사용자 홈 오염 방지·재현성).
# 반드시 airflow import보다 먼저 설정해야 한다.
os.environ.setdefault("AIRFLOW_HOME", str(OUTPUT_DIR / "airflow_home"))
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", str(Path(__file__).resolve().parent))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")

import pendulum  # noqa: E402
from airflow.providers.standard.operators.python import PythonOperator  # noqa: E402
from airflow.sdk import DAG  # noqa: E402

# ── 정제 규칙(7.2절) ─────────────────────────────────────────────
# 표준 코드: 행정표준코드관리시스템(code.go.kr) 법정동코드 시군구 5자리 발췌.
MAPPING_CSV = INPUT_DIR / "lawd_cd_seoul.csv"
# 약칭 보정 사전: 표기 변형(약칭)을 표준명으로 정규화한다.
ALIASES = {"강남": "강남구", "마포": "마포구", "관악": "관악구"}


def load_mapping() -> dict[str, str]:
    """표준명 → 법정동 시군구 코드 매핑을 읽는다."""
    with open(MAPPING_CSV, encoding="utf-8") as f:
        return {row["region_std"]: row["lawd_cd"] for row in csv.DictReader(f)}


def day_dir(ds: str) -> Path:
    d = OUTPUT_DIR / "daily" / ds
    d.mkdir(parents=True, exist_ok=True)
    return d


def dump_json(path: Path, obj) -> None:
    """결정적 직렬화(키 정렬·고정 포맷) — 재실행 산출물 비교(해시)의 전제."""
    path.write_text(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


# ── 태스크 1: 입력 검증 ──────────────────────────────────────────
def validate_input(ds: str, **_) -> int:
    """logical date에 해당하는 입력 파일의 존재·형식을 검증한다.

    입력이 없으면 실패한다 — 실패는 하류 태스크로 전파된다(upstream_failed).
    """
    # 재실행 시작 시 성공 마커부터 제거한다 — 이 run이 실패하면 마커 없는 상태로
    # 남아, 주간 롤업이 이전 성공의 낡은 산출물을 최신인 양 합산하지 못하게 한다.
    (day_dir(ds) / "_SUCCESS").unlink(missing_ok=True)

    path = INPUT_DIR / "complaints" / f"{ds}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"입력 파일 없음: {path} — 해당 날짜({ds})의 원천 데이터가 아직 없거나 "
            "수집 단계가 실패했다. 하류 태스크는 실행되지 않는다."
        )
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            json.loads(line)  # 형식 오류가 있으면 여기서 실패한다
            n += 1
    print(f"[validate_input] {ds}: {n}건 검증 통과 ({path.name})")
    return n


# ── 태스크 2: 정제·표준 코드 매핑 ────────────────────────────────
def clean_and_map(ds: str, **_) -> dict:
    """중복 제거(4주차) → 표기 정규화 → 표준 코드 매핑. 총계 보존을 기록한다."""
    path = INPUT_DIR / "complaints" / f"{ds}.jsonl"
    mapping = load_mapping()

    records = [json.loads(line) for line in open(path, encoding="utf-8")]
    physical = len(records)

    # (1) 중복 접수 제거: 같은 complaint_id의 재전송은 먼저 온 것만 남긴다(4주차 원칙).
    seen: set[str] = set()
    dup_removed: list[str] = []
    valid: list[dict] = []
    for rec in records:
        cid = rec["complaint_id"]
        if cid in seen:
            dup_removed.append(cid)
            continue
        seen.add(cid)
        valid.append(rec)

    # (2) 표기 정규화 → (3) 표준 코드 매핑. 실패는 버리지 않고 분리 기록한다.
    mapped: list[dict] = []
    missing: list[str] = []           # 지역 미기재 complaint_id
    unmapped: list[dict] = []         # 매핑 실패(원문 보존)
    ws_stripped = 0                   # 앞뒤 공백 보정이 실제 적용된 건수
    alias_fixed = 0                   # 약칭 보정이 실제 적용된 건수
    for rec in valid:
        raw = rec.get("region_raw")
        name = (raw or "").strip()
        if raw is not None and name != raw:
            ws_stripped += 1
        if not name:
            missing.append(rec["complaint_id"])
            continue
        if name in ALIASES:
            alias_fixed += 1
        name = ALIASES.get(name, name)
        if name in mapping:
            mapped.append(
                {
                    "complaint_id": rec["complaint_id"],
                    "region_std": name,
                    "lawd_cd": mapping[name],
                    "category": rec["category"],
                    "created_at": rec["created_at"],
                }
            )
        else:
            unmapped.append({"complaint_id": rec["complaint_id"], "region_raw": raw})

    out = day_dir(ds)
    with open(out / "cleaned.jsonl", "w", encoding="utf-8") as f:
        for rec in mapped:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    dump_json(out / "excluded.json", {"dup_removed": dup_removed, "missing": missing, "unmapped": unmapped})

    quality = {
        "date": ds,
        "physical": physical,
        "dup_removed": len(dup_removed),
        "valid": len(valid),
        "mapped": len(mapped),
        "missing": len(missing),
        "unmapped": len(unmapped),
        "ws_stripped": ws_stripped,
        "alias_fixed": alias_fixed,
        # 총계 보존: 입력 전량이 네 갈래(매핑/미기재/미매핑/중복제거) 어딘가에 있어야 한다.
        "preservation_ok": physical == len(mapped) + len(missing) + len(unmapped) + len(dup_removed),
    }
    dump_json(out / "quality.json", quality)
    print(f"[clean_and_map] {ds}: {quality}")
    return quality


# ── 태스크 3a: 일별 집계 ─────────────────────────────────────────
def aggregate_daily(ds: str, **_) -> dict:
    """정제된 레코드를 지역 코드·카테고리별로 집계한다."""
    out = day_dir(ds)
    mapped = [json.loads(line) for line in open(out / "cleaned.jsonl", encoding="utf-8")]

    by_region = Counter((r["lawd_cd"], r["region_std"]) for r in mapped)
    by_category = Counter(r["category"] for r in mapped)
    # 동수(동률)면 가나다순 첫 항목 — 결정적 산출을 위해 규칙을 명시한다.
    # 매핑 0건인 날(전부 미기재·미매핑이거나 빈 입력)도 유효한 날이다 — None으로 표기.
    top_category = (
        sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if by_category else None
    )

    summary = {
        "date": ds,
        "mapped_total": len(mapped),
        "by_region": [
            {"lawd_cd": code, "region": name, "count": cnt}
            for (code, name), cnt in sorted(by_region.items())
        ],
        "by_category": dict(sorted(by_category.items())),
        "top_category": top_category,
    }
    dump_json(out / "daily_summary.json", summary)
    print(f"[aggregate_daily] {ds}: mapped_total={len(mapped)}, top={top_category}")
    return summary


# ── 태스크 3b: 품질 점검(게이트) ─────────────────────────────────
def check_quality(ds: str, **_) -> dict:
    """정제 통계를 점검한다. 총계 보존이 깨지면 태스크를 실패시킨다(품질 게이트)."""
    out = day_dir(ds)
    quality = json.loads((out / "quality.json").read_text(encoding="utf-8"))
    if not quality["preservation_ok"]:
        raise ValueError(f"총계 보존 실패: {quality} — 정제 단계에서 레코드가 사라졌다.")
    # valid=0(빈 입력이거나 전부 중복 제거)도 유효한 날이다 — 비율은 정의 불가로 None.
    valid = quality["valid"]
    check = {
        **quality,
        "missing_rate": round(quality["missing"] / valid, 3) if valid else None,
        "unmapped_rate": round(quality["unmapped"] / valid, 3) if valid else None,
        "gate": "PASS",
    }
    dump_json(out / "quality_check.json", check)
    print(f"[check_quality] {ds}: gate=PASS, unmapped_rate={check['unmapped_rate']}")
    return check


# ── 태스크 4: 일별 보고서 ────────────────────────────────────────
def write_report(ds: str, **_) -> str:
    """집계·품질 결과를 사람이 읽는 일별 보고서로 만든다.

    보고서 내용은 입력의 결정적 함수다(생성 시각 등 비결정 요소를 넣지 않는다)
    — 같은 날짜를 재실행하면 바이트 단위로 같은 보고서가 나와야 한다(재현성).
    """
    out = day_dir(ds)
    summary = json.loads((out / "daily_summary.json").read_text(encoding="utf-8"))
    check = json.loads((out / "quality_check.json").read_text(encoding="utf-8"))
    excluded = json.loads((out / "excluded.json").read_text(encoding="utf-8"))

    lines = [
        f"# 일별 민원 요약 보고서 — {ds}",
        "",
        f"- 원천 접수(물리 레코드): {check['physical']}건",
        f"- 유효 접수(중복 제거 후): {check['valid']}건 (중복 제거 {check['dup_removed']}건)",
        f"- 표준 코드 매핑: {check['mapped']}건 / 지역 미기재 {check['missing']}건 / 매핑 실패 {check['unmapped']}건",
        f"- 총계 보존 검증: {'통과' if check['preservation_ok'] else '실패'} "
        f"({check['physical']} = {check['mapped']} + {check['missing']} + {check['unmapped']} + {check['dup_removed']})",
        "",
        "## 지역별 접수 건수(법정동 시군구 코드 기준)",
        "",
        "| 코드 | 지역 | 건수 |",
        "|---|---|---|",
    ]
    for row in summary["by_region"]:
        lines.append(f"| {row['lawd_cd']} | {row['region']} | {row['count']} |")
    lines += [
        "",
        "## 유형별 접수 건수",
        "",
        "| 유형 | 건수 |",
        "|---|---|",
    ]
    for cat, cnt in summary["by_category"].items():
        lines.append(f"| {cat} | {cnt} |")
    lines += [
        "",
        f"최다 유형: **{summary['top_category'] or '해당 없음(매핑 0건)'}**",
        "",
        "## 매핑 실패 상세(후속 조치 대상)",
        "",
    ]
    if excluded["unmapped"]:
        for item in excluded["unmapped"]:
            lines.append(f"- {item['complaint_id']}: region_raw={item['region_raw']!r} — 표준 코드 사전에 없음")
    else:
        lines.append("- 없음")
    lines += [
        "",
        f"입력: `data/input/complaints/{ds}.jsonl` (시뮬레이션 입력). "
        "본 보고서는 입력의 결정적 산출물이다 — 동일 입력 재실행 시 동일 내용.",
        "",
    ]
    report_path = out / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    # 마지막 태스크까지 성공했을 때만 성공 마커를 기록한다(검증 태스크가 재실행
    # 시작 시 제거) — "이 날짜의 산출물 세트는 완결"의 증표.
    (out / "_SUCCESS").write_text("", encoding="utf-8")
    print(f"[write_report] {ds}: {report_path}")
    return str(report_path)


# ── 주간 롤업 태스크 ─────────────────────────────────────────────
def rollup_weekly(ds: str, logical_date=None, data_interval_end=None, **_) -> dict:
    """일별 산출물(요약·품질)을 주간으로 합산한다 — 원천을 다시 읽지 않는다.

    대상 구간은 7일 창이다 — 전체 디렉터리를 무조건 합치면 몇 주 뒤에는
    '주간'이 아니라 누적 보고서가 되어 버린다. 창의 끝은 실행 방식에 따라 다르다:
    스케줄 실행은 데이터 구간(data interval)의 끝(배타적)의 전날, 수동 실행
    (dag.test — interval 시작=끝=logical date)은 logical date 당일이다.
    구간 안에 일별 산출물이 없는 날짜는 조용히 넘기지 않고 결측으로 기록한다.
    """
    import datetime as dt

    if data_interval_end is not None and logical_date is not None and data_interval_end != logical_date:
        end = data_interval_end.date() - dt.timedelta(days=1)  # interval 끝은 배타적
    else:
        end = dt.date.fromisoformat(ds)
    window = [(end - dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

    daily_root = OUTPUT_DIR / "daily"
    # 파일 존재가 아니라 성공 마커를 기준으로 합산한다 — 마지막 실행이 실패한
    # 날짜의 낡은 산출물이 최신 확정치처럼 섞여 드는 것을 막는다.
    days = [d for d in window if (daily_root / d / "_SUCCESS").exists()]
    days_absent = [d for d in window if d not in days]
    if not days:
        raise FileNotFoundError(
            f"구간 {window[0]}~{window[-1]}에 일별 산출물이 없다 — 일별 DAG가 먼저 성공해야 한다."
        )

    region_total: Counter = Counter()
    category_total: Counter = Counter()
    totals = Counter()
    per_day = []
    for ds in days:
        summary = json.loads((daily_root / ds / "daily_summary.json").read_text(encoding="utf-8"))
        check = json.loads((daily_root / ds / "quality_check.json").read_text(encoding="utf-8"))
        for row in summary["by_region"]:
            region_total[(row["lawd_cd"], row["region"])] += row["count"]
        for cat, cnt in summary["by_category"].items():
            category_total[cat] += cnt
        for key in ("physical", "dup_removed", "mapped", "missing", "unmapped"):
            totals[key] += check[key]
        per_day.append({"date": ds, "mapped": check["mapped"], "physical": check["physical"]})

    weekly = {
        "window_start": window[0],
        "window_end": window[-1],
        "days_absent": days_absent,
        "days": per_day,
        "physical_total": totals["physical"],
        "mapped_total": totals["mapped"],
        "missing_total": totals["missing"],
        "unmapped_total": totals["unmapped"],
        "dup_removed_total": totals["dup_removed"],
        "preservation_ok": totals["physical"]
        == totals["mapped"] + totals["missing"] + totals["unmapped"] + totals["dup_removed"],
        "by_region": [
            {"lawd_cd": code, "region": name, "count": cnt}
            for (code, name), cnt in sorted(region_total.items())
        ],
        "by_category": dict(sorted(category_total.items())),
    }
    # 주간 산출물도 창 끝 날짜로 파티셔닝한다 — 다음 주 실행이 지난주 보고서를
    # 덮어쓰면 감사 추적이 불가능해진다(일별 산출물과 같은 원칙).
    out = OUTPUT_DIR / "weekly" / window[-1]
    out.mkdir(parents=True, exist_ok=True)
    dump_json(out / "weekly_summary.json", weekly)

    lines = [
        f"# 주간 민원 롤업 보고서 — 구간 {window[0]} ~ {window[-1]}",
        "",
        f"- 집계 일수: {len(days)}일 (일별 산출물 집계 — 원천 재스캔 아님), "
        f"산출물 없는 날짜: {', '.join(days_absent) if days_absent else '없음'}",
        f"- 원천 접수 합계: {weekly['physical_total']}건, 매핑 {weekly['mapped_total']}건, "
        f"미기재 {weekly['missing_total']}건, 매핑 실패 {weekly['unmapped_total']}건, "
        f"중복 제거 {weekly['dup_removed_total']}건",
        f"- 총계 보존 검증: {'통과' if weekly['preservation_ok'] else '실패'}",
        "",
        "| 코드 | 지역 | 주간 건수 |",
        "|---|---|---|",
    ]
    for row in weekly["by_region"]:
        lines.append(f"| {row['lawd_cd']} | {row['region']} | {row['count']} |")
    (out / "weekly_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[rollup_weekly] {days[0]}~{days[-1]}: {weekly['by_region']}")
    return weekly


# ── DAG 정의 ─────────────────────────────────────────────────────
with DAG(
    dag_id="daily_complaint_report",
    description="일별 민원 요약 보고서 배치(검증→정제·매핑→집계/품질→보고서)",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 7, 1, tz="UTC"),
    catchup=False,
) as daily_dag:
    t_validate = PythonOperator(task_id="validate_input", python_callable=validate_input)
    t_clean = PythonOperator(task_id="clean_and_map", python_callable=clean_and_map)
    t_aggregate = PythonOperator(task_id="aggregate_daily", python_callable=aggregate_daily)
    t_quality = PythonOperator(task_id="check_quality", python_callable=check_quality)
    t_report = PythonOperator(task_id="write_report", python_callable=write_report)

    # 의존성 선언: 검증 → 정제 → (집계 ∥ 품질) → 보고서
    t_validate >> t_clean >> [t_aggregate, t_quality] >> t_report

with DAG(
    dag_id="weekly_complaint_rollup",
    description="일별 산출물을 주간으로 롤업하는 배치",
    schedule="@weekly",
    start_date=pendulum.datetime(2026, 7, 1, tz="UTC"),
    catchup=False,
) as weekly_dag:
    PythonOperator(task_id="rollup_weekly", python_callable=rollup_weekly)


def bootstrap() -> None:
    """메타데이터 DB 준비 + DAG 직렬화(dag.test의 전제 조건).

    Airflow 3에서 dag.test()는 DAG가 메타데이터 DB에 직렬화되어 있어야 한다.
    """
    env = os.environ.copy()
    for cmd in (["db", "migrate"], ["dags", "reserialize"]):
        subprocess.run(
            [sys.executable, "-m", "airflow", *cmd],
            check=True, env=env, capture_output=True,
        )


if __name__ == "__main__":
    bootstrap()
    run = daily_dag.test(logical_date=pendulum.datetime(2026, 7, 1, tz="UTC"))
    print(f"단독 실행 결과: dagrun={run.state}")
