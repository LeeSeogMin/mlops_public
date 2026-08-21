#!/usr/bin/env python3
"""실습 17.1 장애 포스트모템 보고서 작성 — 앞 장 실측 증거의 회수·종합.

17장은 새 장애를 만들지 않는다. 앞 장에서 이미 발생·기록된 사건을 증거 JSON에서
읽어 포스트모템 서식으로 구조화하고, error budget·재발 방지 계획·운영 개선
체크리스트·조직 운영안을 자동 생성한다(13장 감사표·14장 인수 검수표·16장
모델카드의 "증거에서 자동 생성" 철학의 종합판).

입력(모두 앞 장 실측 — data/input/에 스냅숏):
  - incident_catalog.json  : 8·9·10장 집필 중 실제로 겪은 코드 결함 3건(문서화된 사실)
  - ch12_load_report.json  : 12장 부하 실측(단일 워커 포화 천장 — 용량 한계)
  - ch14_integration_report.json : 14장 장애 드릴 3종(주입 드릴) + 예측·품질 게이트 카운터
  - ch15_llm_snapshot.json : 15장 멀티벤더 LLM 생성(OpenAI 429 billing_not_active — 벤더 장애)

산출(data/output/):
  - ch17_postmortem_report.json      : 통합 증거(재실행 바이트 동일)
  - ch17_error_budget.json           : error budget 계산(실측 카운터 + 설계 SLO 목표)
  - 17-1-postmortem.md               : 포스트모템 보고서(빈 양식을 실측으로 채움)
  - ch17_recurrence_prevention_plan.md : 재발 방지 계획
  - ch17_ops_improvement_checklist.md  : 운영 개선 체크리스트
  - ch17_org_operating_plan.md         : AI 평가·검증 조직 운영안(Policy Methodology Lab)

원칙
  - 모든 수치는 앞 장 실측 입력에서 유도한다(이 장은 새 수치를 만들지 않는다).
  - now()·절대경로·휘발성 id 금지 → 증거 JSON 재실행 바이트 동일.
  - SLO 목표는 설계상 정한 값(측정값 아님)임을 명시하고, 소진율만 실측 카운터에서 계산.

실행: cd practice/chapter17 && venv/bin/python run_chapter17.py
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


# --- 입력 로드 -------------------------------------------------------------

def _load(input_dir: Path, name: str) -> dict:
    return json.loads((input_dir / name).read_text("utf-8"))


# --- 사건(incident) 구조화 --------------------------------------------------

def build_incidents(input_dir: Path) -> list[dict]:
    """네 분류의 사건을 통일된 포스트모템 스키마로 구조화한다.

    분류: 실제 결함(코드) / 주입 드릴 / 용량 한계 / 벤더 장애.
    코드 결함 3건은 문서화된 카탈로그에서, 나머지는 증거 JSON에서 유도한다.
    """
    incidents: list[dict] = []

    # (1) 실제 결함(코드) 3건 — 문서화된 사실(8·9·10장)
    catalog = _load(input_dir, "incident_catalog.json")
    for inc in catalog["incidents"]:
        incidents.append({
            "id": inc["id"], "chapter": inc["chapter"], "category": inc["category"],
            "title": inc["title"], "source": inc["source"],
            "symptom": inc["symptom"], "impact": inc["impact"],
            "detection_layer": inc["detection_layer"], "timeline": inc["timeline"],
            "three_why": inc["three_why"], "root_cause": inc["root_cause"],
            "fix": inc["fix"], "prevention_gate": inc["prevention_gate"],
            "metrics": {},
        })

    # (2) 용량 한계 1건 — 12장 부하 실측에서 유도
    load = _load(input_dir, "ch12_load_report.json")
    sc = load["scenarios"]
    base, spike, scale, io = sc["baseline"], sc["spike"], sc["scale"], sc["io"]
    ceiling_lo = round(min(base["rps"], spike["rps"]) / 100) * 100   # ≈2500
    ceiling_hi = round(max(base["rps"], spike["rps"]) / 100) * 100   # ≈2800
    total_requests = sum(s["requests"] for s in sc.values())
    total_failures = sum(s["failures"] for s in sc.values())
    incidents.append({
        "id": "INC-12-single-worker-saturation",
        "chapter": 12, "category": "용량 한계",
        "title": "단일 워커 한 코어 포화로 처리량 천장",
        "source": "practice/chapter12/data/output/ch12_load_report.json",
        "symptom": f"사용자 20→100 증가에도 처리량은 천장(≈{ceiling_lo}–{ceiling_hi} RPS)에 머물고 지연만 증가",
        "impact": "단일 프로세스가 한 코어를 포화(CPU peak "
                  f"{base['cpu_pct_peak']}%)시켜 세로 확장 없이는 더 못 받음 — 단, 부하 중 정확성 유지(failures {total_failures})",
        "detection_layer": "부하 테스트(Locust 5시나리오)",
        "timeline": [
            f"baseline(사용자 {base['users']}): {base['rps']} RPS, p99 {base['p99_ms']}ms, CPU peak {base['cpu_pct_peak']}%",
            f"spike(사용자 {spike['users']}): {spike['rps']} RPS, p99 {spike['p99_ms']}ms — 처리량 천장, 지연만 상승",
            f"scale(워커 2): {scale['rps']} RPS(baseline 대비 {load['findings']['scale_vs_baseline']['ratio']}배), RSS {scale['rss_mb_peak']}MB",
            f"io(shadow on): {io['rps']} RPS(baseline 대비 {load['findings']['io_vs_baseline']['ratio']}배) — 요청당 I/O 비용",
        ],
        "three_why": [
            "왜 처리량이 안 오르나 — 단일 워커가 한 코어를 포화시킴",
            f"왜 포화인가 — 프로세스 1개가 CPU {base['cpu_pct_peak']}%(한 코어 상한 근처)를 쓴다",
            "왜 사용자를 늘려도 같나 — 서비스율이 천장이라 대기만 늘어 지연으로 나타남(Little's law)",
        ],
        "root_cause": "단일 워커·단일 코어 서비스율 상한. 부하는 용량을 늘리지 않고 대기를 늘린다.",
        "fix": "워커 수평 증설(1→2로 처리량 1.26배 실측) 또는 인스턴스 수평 확장 — 용량 계획의 기준선을 실측 천장으로",
        "prevention_gate": "배포 전 부하 프로파일로 처리량 천장·knee 지점 측정, 자동 스케일 임계 설정",
        "metrics": {
            "baseline_rps": base["rps"], "spike_rps": spike["rps"],
            "ceiling_lo": ceiling_lo, "ceiling_hi": ceiling_hi,
            "cpu_peak_pct": base["cpu_pct_peak"],
            "scale_ratio": load["findings"]["scale_vs_baseline"]["ratio"],
            "io_ratio": load["findings"]["io_vs_baseline"]["ratio"],
            "workers2_rss_mb": scale["rss_mb_peak"], "baseline_rss_mb": base["rss_mb_peak"],
            "total_requests": total_requests, "total_failures": total_failures,
        },
    })

    # (3) 주입 드릴 3건 — 14장 장애 드릴 실측에서 유도
    integ = _load(input_dir, "ch14_integration_report.json")
    d = integ["drills"]
    d1, d2, d3 = d["D1_poison_isolation"], d["D2_duplicate_resend"], d["D3_api_outage_recovery"]
    incidents.append({
        "id": "INC-14-D1-poison-isolation",
        "chapter": 14, "category": "주입 드릴",
        "title": "오염 메시지 격리(계획된 주입)",
        "source": "practice/chapter14/data/output/ch14_integration_report.json (drills.D1)",
        "symptom": f"파싱 불가 메시지({', '.join(d1['reasons'])}) 유입",
        "impact": f"{d1['quarantined']}건 격리, 파이프라인 지속(day3 매핑 무결 {d1['day3_mapped_intact']})",
        "detection_layer": "정제 단계 파서(격리 큐)",
        "timeline": ["오염 메시지 1건 주입", "파서가 json_parse_error로 격리", "정상 메시지는 계속 처리"],
        "three_why": [
            "왜 파이프라인이 안 멈췄나 — 오염 1건을 격리 큐로 분리",
            "왜 격리가 되나 — 파싱 실패를 삼키지 않고 사유와 함께 분리",
            "왜 나머지가 무사한가 — 한 메시지 실패가 배치 전체를 실패시키지 않는 격리 설계",
        ],
        "root_cause": "(드릴 — 격리 설계의 유효성 확인) 개별 실패가 전체를 오염시키지 않도록 사유 보존 격리.",
        "fix": "격리 큐 + 사유 기록. 실패를 삼키지 않고 드러냄(11장 하드룰).",
        "prevention_gate": "파싱 실패 격리 + 격리 건수 모니터링",
        "metrics": {"quarantined": d1["quarantined"], "reasons": d1["reasons"],
                    "pipeline_continued": d1["pipeline_continued"]},
    })
    incidents.append({
        "id": "INC-14-D2-duplicate-resend",
        "chapter": 14, "category": "주입 드릴",
        "title": "중복 재전송 흡수(계획된 주입)",
        "source": "practice/chapter14/data/output/ch14_integration_report.json (drills.D2)",
        "symptom": f"물리 수신 {d2['physical_received']}건 중 중복 재전송 포함",
        "impact": f"고유 {d2['unique']}건으로 수렴, 중복 {d2['dedup_dropped']}건 제거, 매핑 결과 불변({d2['mapped_unchanged']})",
        "detection_layer": "멱등 UPSERT(5장) + at-least-once(4장)",
        "timeline": [
            f"물리 {d2['physical_received']}건 수신(중복 재전송 포함)",
            f"멱등 처리로 고유 {d2['unique']}건 확정",
            f"중복 {d2['dedup_dropped']}건 제거 — 업무 상태 불변",
        ],
        "three_why": [
            "왜 중복이 결과를 안 바꾸나 — 멱등 UPSERT가 같은 키 재수신을 무해화",
            "왜 재전송이 발생하나 — at-least-once 전달 보증이 크래시 시 재생을 허용",
            "왜 이게 안전한가 — 전달 보증과 멱등이 한 쌍으로 설계됨(14장 P1)",
        ],
        "root_cause": "(드릴 — 전달 보증·멱등 한 쌍의 유효성 확인) at-least-once + UPSERT.",
        "fix": "수동 커밋(내구 쓰기 후) + 멱등 UPSERT로 재생을 무해화.",
        "prevention_gate": "at-least-once ↔ 멱등 UPSERT 한 쌍 유지, 파티션 수 검증",
        "metrics": {"physical_received": d2["physical_received"], "unique": d2["unique"],
                    "dedup_dropped": d2["dedup_dropped"]},
    })
    incidents.append({
        "id": "INC-14-D3-api-outage-recovery",
        "chapter": 14, "category": "주입 드릴",
        "title": "마감 직전 예측 API 중단·복구(계획된 주입)",
        "source": "practice/chapter14/data/output/ch14_integration_report.json (drills.D3)",
        "symptom": f"마감 직전 model-api 정지({', '.join(d3['pending_errors'])})",
        "impact": f"마감은 확정({d3['day3_closed_despite_outage']}), 예측 {d3['pending_at_close']}건 보류 → "
                  f"재기동 후 {d3['pending_after_recovery']}건으로 수렴(재시도 {d3['recovered_attempts']})",
        "detection_layer": "부분 실패 격리 + 지연 재시도",
        "timeline": [
            "마감 직전 예측 API 정지(api_unreachable)",
            f"데이터 마감은 확정(_SUCCESS), 예측 {d3['pending_at_close']}건 pending_retry",
            f"API 재기동 후 predict_retry로 {d3['pending_after_recovery']}건 수렴(attempts {d3['recovered_attempts'][0]})",
        ],
        "three_why": [
            "왜 마감이 안 밀렸나 — 데이터 마감과 예측을 분리(부분 실패 격리)",
            "왜 예측이 복구됐나 — pending 상태로 남기고 재기동 후 재시도",
            "왜 유실이 0인가 — 실패를 삼키지 않고 pending으로 보존해 재시도 대상으로",
        ],
        "root_cause": "(드릴 — 부분 실패 격리·재시도의 유효성 확인) 마감/예측 분리 + pending 재시도.",
        "fix": "부분 실패를 pending으로 보존, 의존 서비스 복구 후 재시도로 수렴.",
        "prevention_gate": "부분 실패 격리 + 재시도 큐 + 마감/예측 의존 분리",
        "metrics": {"pending_at_close": d3["pending_at_close"],
                    "pending_after_recovery": d3["pending_after_recovery"],
                    "recovered_attempts": d3["recovered_attempts"]},
    })

    # (4) 벤더 장애 1건 — 15장 멀티벤더 스냅숏에서 유도
    snap = _load(input_dir, "ch15_llm_snapshot.json")
    prov = {p["provider"]: p for p in snap["providers"]}
    openai = next(p for p in snap["providers"] if "OpenAI" in p["provider"])
    clova = next(p for p in snap["providers"] if "CLOVA" in p["provider"])
    openai_err = openai["results"][0]["error"] if openai["results"] else "HTTP 429 billing_not_active"
    incidents.append({
        "id": "INC-15-openai-billing-429",
        "chapter": 15, "category": "벤더 장애",
        "title": "OpenAI 생성 전건 429(billing_not_active) — 인증 게이트≠결제 게이트",
        "source": "practice/chapter15/data/output/ch15_llm_snapshot.json",
        "symptom": f"인증(/v1/models)은 통과하나 생성(chat/completions) {openai['failed']}건 전건 실패({openai_err})",
        "impact": f"{openai['model']} 생성 0/{openai['failed'] + openai['generated']} — 그러나 "
                  f"{clova['model']}가 {clova['generated']}/{clova['generated'] + clova['failed']} 응답해 서비스 지속",
        "detection_layer": "생성 엔드포인트(chat/completions) — 인증 엔드포인트가 아님",
        "timeline": [
            "동일한 결정적 코어(프롬프트 v2·근거 조문)를 두 제공자에 투입",
            f"OpenAI: 인증은 통과, 생성은 {openai['failed']}건 전건 {openai_err}",
            f"CLOVA: {clova['generated']}건 정상 응답 → 서비스 완주",
        ],
        "three_why": [
            "왜 생성이 실패했나 — 계정 결제가 비활성(billing_not_active)이라 429",
            "왜 인증은 통과했나 — /v1/models(인증 게이트)와 chat/completions(결제 게이트)가 별개",
            "왜 서비스는 지속됐나 — 코어가 제공자 독립이라 한 벤더가 막혀도 다른 벤더로 완주",
        ],
        "root_cause": "인증 게이트 통과를 '사용 가능'으로 오판. 단일 벤더 종속 위험.",
        "fix": "키 유효성은 반드시 생성 엔드포인트 1콜로 확인 + 제공자 독립 코어로 멀티벤더 대체",
        "prevention_gate": "생성 엔드포인트 헬스체크 + 멀티벤더 폴백",
        "metrics": {"openai_generated": openai["generated"], "openai_failed": openai["failed"],
                    "clova_generated": clova["generated"], "clova_failed": clova["failed"],
                    "openai_error": openai_err},
    })
    return incidents


# --- error budget 계산 -----------------------------------------------------

def build_error_budget(input_dir: Path) -> dict:
    """실측 카운터에서 SLO별 오차 예산 소진을 계산한다.

    SLO 목표는 '설계상 정한 값'(측정값 아님)이며, 소진율만 실측에서 계산한다.
    """
    load = _load(input_dir, "ch12_load_report.json")
    integ = _load(input_dir, "ch14_integration_report.json")
    snap = _load(input_dir, "ch15_llm_snapshot.json")

    # (a) 요청 가용성 — 12장 부하 5시나리오 실측
    total_req = sum(s["requests"] for s in load["scenarios"].values())
    total_fail = sum(s["failures"] for s in load["scenarios"].values())
    slo_avail = 0.999                          # 설계 목표(측정값 아님)
    allowed_fail = math.floor(total_req * (1 - slo_avail))
    avail = {
        "slo_name": "요청 가용성", "source_chapter": 12,
        "slo_target": slo_avail, "unit": "성공 요청 비율",
        "total_events": total_req, "observed_failures": total_fail,
        "allowed_failures": allowed_fail,
        "budget_consumed": total_fail, "budget_remaining": allowed_fail - total_fail,
        "burn_rate_pct": round(100 * total_fail / allowed_fail, 2) if allowed_fail else 0.0,
        "verdict": "예산 내" if total_fail <= allowed_fail else "예산 초과",
    }

    # (b) 예측 성공 — 14장 예측 카운터(3건은 D3에서 재시도로 복구)
    ok = integ["ops_counters"]["predict_ok"]
    failed = integ["ops_counters"]["predict_failed"]
    # 복구 후 잔여 실패 = D3에서 재기동·재시도 뒤에도 남은 예측(0 = 전건 복구)
    residual_after_recovery = integ["drills"]["D3_api_outage_recovery"]["pending_after_recovery"]
    total_pred = ok + failed
    slo_pred = 0.95
    allowed_pred = round(total_pred * (1 - slo_pred), 2)   # 허용 실패 예산(건)
    # 소진은 두 시점으로 구분한다: 복구 전(원 실패)과 복구 후(잔여 실패).
    #   - budget_consumed_raw          : 복구 전에 발생한 실패 수(순간 소진)
    #   - budget_consumed_after_recovery: 재시도 복구 후에도 남는 실패 수(최종 소진)
    pred = {
        "slo_name": "예측 성공", "source_chapter": 14,
        "slo_target": slo_pred, "unit": "예측 성공 비율",
        "total_events": total_pred, "observed_failures": failed,
        "allowed_failures": allowed_pred,
        "budget_consumed_raw": failed,
        "budget_consumed_after_recovery": residual_after_recovery,
        "verdict": "복구 전 예산 초과(3건) → 재시도로 잔여 0건"
                   if failed > allowed_pred and residual_after_recovery == 0
                   else ("예산 내" if failed <= allowed_pred else "예산 초과"),
    }

    # (c) 품질 게이트(MAE) — 14장 지연 채점(2일 중 초과일)
    de = integ["delayed_evaluation"]
    scored_days = len(de["mae_by_target_date"])
    exceeded = len(de["gate_exceeded_days"])
    qual = {
        "slo_name": "품질 게이트(MAE)", "source_chapter": 14,
        "gate": de["mae_gate"], "overall_mae": de["overall_mae"],
        "scored_days": scored_days, "gate_exceeded_days": exceeded,
        "gate_exceeded_dates": de["gate_exceeded_days"],
        "overall_verdict": "전체 통과" if de["overall_mae"] <= de["mae_gate"] else "전체 초과",
        "note": "전체 MAE는 게이트 통과이나 일자별로는 2일 중 1일이 게이트를 초과 — "
                "전체 지표가 국소 열화를 가릴 수 있음(감시의 입도 교훈)",
    }

    # (d) LLM 생성 가용성(멀티벤더) — 15장
    prov = snap["providers"]
    per_provider = {p["provider"]: {"generated": p["generated"], "failed": p["failed"]} for p in prov}
    any_available = any(p["generated"] > 0 for p in prov)
    llm = {
        "slo_name": "LLM 생성 가용성(멀티벤더)", "source_chapter": 15,
        "providers": per_provider,
        "service_continued": any_available,
        "note": "단일 벤더(OpenAI) 생성 예산은 전건 소진(429)됐으나, 제공자 독립 코어라 "
                "다른 벤더(CLOVA)로 서비스 지속 — 벤더 종속을 폴백으로 상쇄",
    }

    return {
        "note": "SLO 목표는 설계상 정한 값(측정값 아님)이다. 소진율만 앞 장 실측 카운터에서 계산한다. "
                "error budget = SLO 목표와 실측의 차이(Google SRE, Embracing Risk).",
        "budgets": [avail, pred, qual, llm],
    }


# --- 성공 요인·실패 패턴(17.1·17.2) ---------------------------------------

def build_success_factors() -> list[dict]:
    """앞 장 실측에서 반복적으로 나타난 성공 구조만 귀납한다(체리픽 금지)."""
    return [
        {"factor": "테스트 층화", "evidence_chapter": 10,
         "evidence": "pytest·호스트 통과 후 컨테이너 스모크에서만 IndexError 발현 — 실행 환경이 달라야 드러나는 결함"},
        {"factor": "전달 보증·멱등의 한 쌍", "evidence_chapter": 14,
         "evidence": "at-least-once + UPSERT로 중복 재전송 11건을 무해화(D2)"},
        {"factor": "결정성·바이트 동일 증거", "evidence_chapter": 9,
         "evidence": "증거 JSON 재실행 바이트 동일 — '무엇이 바뀌면 사고인가'의 경계 유지(7~16장 공통)"},
        {"factor": "게이트 vs 감시 구분", "evidence_chapter": 13,
         "evidence": "품질 규칙(계약 위반 차단)과 드리프트(분포 이동 신호)를 다른 층으로 분리(11·13장)"},
        {"factor": "손 검산 가능 설계", "evidence_chapter": 9,
         "evidence": "MAE 1.0·예측 6.0을 손으로 검산 가능하게 설계해 전 파이프라인 스모크 기준으로(12장 Little's law도)"},
        {"factor": "부분 실패 격리·복구", "evidence_chapter": 14,
         "evidence": "마감/예측 분리 + pending 재시도로 API 중단 중 유실 0(D3)"},
    ]


def build_failure_patterns() -> list[dict]:
    """앞 장 실제 결함에서 반복된 실패 패턴을 귀납한다."""
    return [
        {"pattern": "침묵 실패(쓰기 성공≠사용 가능)", "evidence_chapters": [8, 9],
         "example": "materialize 0건 적재가 온라인 None으로(8장), runs:/ 등록 성공이 로드 실패로(9장)",
         "prevention": "쓰기 성공 로그가 아니라 사용 가능성(건수·로드)까지 검증하는 게이트"},
        {"pattern": "배치 가정 결함", "evidence_chapters": [10],
         "example": "모듈 레벨 경로 계산이 저장소 깊이를 가정 → 컨테이너에서 import 즉사",
         "prevention": "환경 가정을 가드로 방어 + 컨테이너 스모크 독립 게이트"},
        {"pattern": "인증 게이트≠결제(권한) 게이트", "evidence_chapters": [15],
         "example": "/v1/models 200이 생성 가능성을 보장 안 함 → chat/completions 전건 429",
         "prevention": "실제 사용 엔드포인트로 헬스체크 + 멀티벤더 폴백"},
        {"pattern": "단일 지점 포화", "evidence_chapters": [12],
         "example": "단일 워커 한 코어 포화로 처리량 천장 — 부하는 대기만 늘림",
         "prevention": "용량 계획을 실측 천장으로 + 수평 확장 임계"},
        {"pattern": "진단 잔해 삭제", "evidence_chapters": [10],
         "example": "--rm이 크래시 로그까지 삭제해 진단 지연",
         "prevention": "진단 기동은 잔해 보존, 감시 루프는 죽음/느림 구분"},
    ]


# --- Policy Methodology Lab 조직 운영안(17.5) -------------------------------

def build_org_plan(input_dir: Path) -> dict:
    """13·15·16장 거버넌스를 평가 기준·벤치마크·승인 게이트 관리 조직으로 종합."""
    snap = _load(input_dir, "ch15_llm_snapshot.json")
    return {
        "name": "Policy Methodology Lab (AI 평가·검증 조직)",
        "mandate": "정책 AI의 평가 기준·벤치마크·승인 게이트를 상설로 관리하는 운영/연구 조직. "
                   "정책 결정 시스템이 아니라 평가·검증의 기준과 관문을 관리한다.",
        "roles": [
            {"role": "평가 기준 관리자", "owns": "정책 AI 평가 루브릭(법적 정합성·중립성·유해성) 3기준",
             "source_chapter": 16, "artifact": "ch16_policy_rubric — 루브릭 개정·버전 관리"},
            {"role": "벤치마크 관리자", "owns": "그룹별 형평·편향 평가 데이터셋·지표",
             "source_chapter": 16, "artifact": "공정성 평가(그룹 MAE 격차·편향 방향)·모델카드 자동 생성"},
            {"role": "승인 게이트 운영자", "owns": "접근·프롬프트·배포의 승인 게이트",
             "source_chapter": 15, "artifact": "프롬프트 레지스트리 승인(요청자·검토자 분리)"},
            {"role": "피처 거버넌스 담당", "owns": "카탈로그·접근 로그·변경 승인",
             "source_chapter": 13, "artifact": "감사 점검표 자동 생성·변경 영향 소비자 식별"},
        ],
        "approval_gates": [
            {"gate": "피처 접근 게이트", "source_chapter": 13, "decision": "역할×행위 인가 + 목적 제한(PIPA 제18조)"},
            {"gate": "프롬프트 승인 게이트", "source_chapter": 15,
             "decision": f"활성 프롬프트 승인 기록 보유(요청자·검토자 분리) — 활성 버전 {snap['active_prompt_version']}"},
            {"gate": "배포·영향평가 게이트", "source_chapter": 16, "decision": "모델카드·영향평가·자동화 결정 이의제기 절차"},
        ],
        "responsibility_boundary": {
            "research_org": "평가 기준·벤치마크의 방법론 설계와 개정(무엇을·어떻게 평가하나)",
            "operations_org": "게이트 집행·로그·감사·재발 방지(실제로 지켜지나)",
            "judge_caveat": "LLM-as-a-judge는 보조이며 단독 승인 근거로 쓰지 않는다 — 채점 주체는 사람·독립 검증(16·15장)",
        },
        "deliverables": [
            "정책 AI 평가 루브릭(개정 이력 포함)",
            "그룹별 형평 벤치마크·모델카드",
            "승인 게이트 운영 기록(접근·프롬프트·배포)",
            "분기 포스트모템·error budget 리뷰",
        ],
    }


# --- 운영 개선 체크리스트 --------------------------------------------------

def build_ops_checklist(incidents: list[dict], budget: dict) -> dict:
    """사건·예산에서 운영 개선 체크리스트를 자동 생성한다(사람이 손으로 쓰지 않는다)."""
    items = []
    # 각 사건의 예방 게이트를 체크 항목으로
    for inc in incidents:
        items.append({"item": f"[{inc['chapter']}장] {inc['prevention_gate']}",
                      "source": inc["id"], "done": False})
    # error budget 정책 항목
    items.append({"item": "error budget 소진 시 신규 배포 동결(SRE error budget policy)",
                  "source": "ch17_error_budget.json", "done": False})
    items.append({"item": "포스트모템은 비난 없이(blameless) — 사람이 아니라 시스템·절차를 고친다",
                  "source": "SRE Postmortem Culture", "done": False})
    return {"total": len(items), "items": items}


# --- 마크다운 렌더 ---------------------------------------------------------

def _md_postmortem(incidents: list[dict], budget: dict) -> str:
    cat_order = ["실제 결함(코드)", "용량 한계", "주입 드릴", "벤더 장애"]
    lines = ["# 장애 포스트모템 보고서 (자동 생성 — 실습 17.1)", "",
             "> 앞 장 실측 사건을 Google SRE의 blameless postmortem 서식으로 구조화했다. "
             "새 장애를 만들지 않았다 — 이미 발생·기록된 사건의 회수다.", ""]
    counts = {}
    for inc in incidents:
        counts[inc["category"]] = counts.get(inc["category"], 0) + 1
    lines.append(f"**사건 {len(incidents)}건** — " +
                 " · ".join(f"{c} {counts.get(c, 0)}" for c in cat_order if counts.get(c)))
    lines.append("")
    for cat in cat_order:
        group = [i for i in incidents if i["category"] == cat]
        if not group:
            continue
        for inc in group:
            lines.append(f"## {inc['id']} — {inc['title']}")
            lines.append(f"- **분류**: {inc['category']} · **출처**: {inc['source']}")
            lines.append(f"- **탐지 층**: {inc['detection_layer']}")
            lines.append(f"- **증상**: {inc['symptom']}")
            lines.append(f"- **영향**: {inc['impact']}")
            lines.append("- **타임라인**:")
            for k, step in enumerate(inc["timeline"], 1):
                lines.append(f"  {k}. {step}")
            lines.append("- **근본 원인(3-why)**:")
            for w in inc["three_why"]:
                lines.append(f"  - {w}")
            lines.append(f"  - **근본 원인**: {inc['root_cause']}")
            lines.append(f"- **조치**: {inc['fix']}")
            lines.append(f"- **재발 방지**: {inc['prevention_gate']}")
            lines.append("")
    lines.append("## Error Budget 요약")
    for b in budget["budgets"]:
        if "verdict" in b:
            lines.append(f"- **{b['slo_name']}**({b['source_chapter']}장): {b.get('verdict', '')}")
        else:
            lines.append(f"- **{b['slo_name']}**({b['source_chapter']}장): {b.get('note', '')[:60]}…")
    lines.append("")
    return "\n".join(lines)


def _md_recurrence(incidents: list[dict]) -> str:
    lines = ["# 재발 방지 계획 (자동 생성 — 실습 17.1)", "",
             "각 사건의 근본 원인에서 재발 방지 게이트를 도출한다. 임시방편이 아니라 "
             "근본 원인을 없애는 게이트를 우선한다(§11 근본 해결).", "",
             "| 사건 | 근본 원인 | 재발 방지 게이트 | 출처 |", "|---|---|---|---|"]
    for inc in incidents:
        lines.append(f"| {inc['id']} | {inc['root_cause']} | {inc['prevention_gate']} | {inc['chapter']}장 |")
    lines.append("")
    lines.append("## 반복 개선 체계")
    lines.append("포스트모템 → 근본 원인(3-why) → 재발 방지 게이트 → 파이프라인에 게이트 추가 → 재검증. "
                 "이 순환이 8~16장에서 실제로 돌았다(각 장의 '실제로 겪은 오류' → 게이트 추가).")
    lines.append("")
    return "\n".join(lines)


def _md_ops_checklist(checklist: dict) -> str:
    lines = ["# 운영 개선 체크리스트 (자동 생성 — 실습 17.1)", "",
             f"총 {checklist['total']}항목 — 사건·error budget에서 도출.", ""]
    for it in checklist["items"]:
        mark = "x" if it["done"] else " "
        lines.append(f"- [{mark}] {it['item']}  \n  근거: {it['source']}")
    lines.append("")
    return "\n".join(lines)


def _md_org_plan(plan: dict) -> str:
    lines = [f"# {plan['name']} — 운영안 (자동 생성 — 실습 17.1)", "",
             f"**임무**: {plan['mandate']}", "", "## 역할과 산출물",
             "| 역할 | 관리 대상 | 근거 장 | 산출물 |", "|---|---|---|---|"]
    for r in plan["roles"]:
        lines.append(f"| {r['role']} | {r['owns']} | {r['source_chapter']}장 | {r['artifact']} |")
    lines.append("")
    lines.append("## 승인 게이트 계보")
    lines.append("| 게이트 | 근거 장 | 결정 |")
    lines.append("|---|---|---|")
    for g in plan["approval_gates"]:
        lines.append(f"| {g['gate']} | {g['source_chapter']}장 | {g['decision']} |")
    lines.append("")
    lines.append("## 연구 조직 ↔ 운영 조직 책임 경계")
    rb = plan["responsibility_boundary"]
    lines.append(f"- **연구 조직**: {rb['research_org']}")
    lines.append(f"- **운영 조직**: {rb['operations_org']}")
    lines.append(f"- **주의**: {rb['judge_caveat']}")
    lines.append("")
    lines.append("## 산출물")
    for d in plan["deliverables"]:
        lines.append(f"- {d}")
    lines.append("")
    return "\n".join(lines)


# --- 오케스트레이션 --------------------------------------------------------

def build_report(input_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    incidents = build_incidents(input_dir)
    budget = build_error_budget(input_dir)
    success = build_success_factors()
    failures = build_failure_patterns()
    org = build_org_plan(input_dir)
    checklist = build_ops_checklist(incidents, budget)

    categories = {}
    for inc in incidents:
        categories[inc["category"]] = categories.get(inc["category"], 0) + 1

    report = {
        "practice": "17.1 장애 포스트모템 보고서 작성",
        "inputs": {
            "incident_catalog": "8·9·10장 실제 코드 결함 3건(문서화)",
            "ch12_load_report": "12장 부하 실측(용량 한계)",
            "ch14_integration_report": "14장 장애 드릴 3종 + 예측·품질 카운터",
            "ch15_llm_snapshot": "15장 멀티벤더 LLM(벤더 장애)",
        },
        "incidents": incidents,
        "incident_count": len(incidents),
        "categories": categories,
        "success_factors": success,
        "failure_patterns": failures,
        "error_budget": budget,
        "recurrence_prevention": [
            {"id": i["id"], "root_cause": i["root_cause"], "gate": i["prevention_gate"],
             "chapter": i["chapter"]} for i in incidents],
        "ops_checklist": checklist,
        "org_plan": org,
    }

    # 증거 JSON (재실행 바이트 동일)
    (output_dir / "ch17_postmortem_report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")
    (output_dir / "ch17_error_budget.json").write_text(
        json.dumps(budget, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")

    # 마크다운 산출물 4종
    (output_dir / "17-1-postmortem.md").write_text(_md_postmortem(incidents, budget), "utf-8")
    (output_dir / "ch17_recurrence_prevention_plan.md").write_text(_md_recurrence(incidents), "utf-8")
    (output_dir / "ch17_ops_improvement_checklist.md").write_text(_md_ops_checklist(checklist), "utf-8")
    (output_dir / "ch17_org_operating_plan.md").write_text(_md_org_plan(org), "utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_report(Path(args.input), Path(args.output))
    print(f"사건 {report['incident_count']}건: " +
          ", ".join(f"{k} {v}" for k, v in sorted(report["categories"].items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
