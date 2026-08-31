#!/usr/bin/env python3
"""14주차 실습 오케스트레이션: LLMOps 결정적 코어 실행 + PASS 게이트.

  1. 코퍼스(개인정보 보호법 조문) 로드 → 프롬프트 레지스트리·RAG·위험 통제·승인·체크리스트 생성
  2. 결정적 증거 JSON(ch14_llmops_report.json, ch14_audit_checklist.json) 저장
  3. PASS 게이트: 실습이 시연하려는 불변식을 코드로 검증

실제 LLM 생성(비결정)은 이 오케스트레이터에 포함하지 않는다 — 14-2-llm-snapshot.py가
게이트 밖에서 1회 스냅샷을 만든다. 이 게이트는 API 키 없이 오프라인으로 통과한다.

실행: cd practice/chapter14 && venv/bin/python run_chapter14.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CODE = BASE_DIR / "code" / "14-1-prompt-registry.py"
INPUT = BASE_DIR / "data" / "input"
OUTPUT = BASE_DIR / "data" / "output"


def _load_module():
    spec = importlib.util.spec_from_file_location("prompt_registry", CODE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not (INPUT / "corpus_pipa.json").exists():
        print(f"코퍼스 없음: {INPUT}/corpus_pipa.json — code/00-build-corpus.py 먼저 실행",
              file=sys.stderr)
        return 2

    mod = _load_module()
    report = mod.build_report(INPUT, OUTPUT)

    reg = report["prompt_registry"]
    rr = report["retrieval_and_risk"]
    ap = report["approval"]
    audit = report["risk_checklist"]

    print(f"=== 15.3 RAG 코퍼스: {report['corpus']['documents']}조문"
          f"({report['corpus']['law']}) ===")
    print("=== 15.4 프롬프트 레지스트리 ===")
    for v in reg["versions"]:
        print(f"  {v['version']}({v['hash8']}) 상태:{v['status']} 길이:{v['char_len']}")
    print(f"=== 15.5 위험 통제: 질의 {rr['total_queries']}건 ===")
    for q in rr["query_log"]:
        extra = ""
        if q["top_doc"]:
            extra = f" [{q['top_doc']} {q['top_score']}]"
        print(f"  {q['qid']}({q['category']}) → {q['decision']}{extra}")
    print(f"  인젝션 차단 {rr['injection_blocked']} / PII 질의 {rr['pii_queries']}"
          f"(마스킹 토큰 {rr['pii_tokens_masked']}) / 검색 {rr['retrieved']}"
          f" / 근거충분 {rr['grounded']} / 근거부족 {rr['insufficient_grounding']}")
    print(f"=== 15.6 승인: {ap['from_version']}→{ap['to_version']} {ap['decision']} ===")
    print(f"=== 위험 체크리스트: {audit['passed']}/{audit['total']} ===")

    # PASS 게이트 — 결정적 불변식
    failures = []
    if report["corpus"]["documents"] != 7:
        failures.append(f"코퍼스 조문 {report['corpus']['documents']}≠7")
    if [v["version"] for v in reg["versions"]] != ["v1", "v2"] or reg["active_version"] != "v2":
        failures.append("프롬프트 레지스트리 버전/활성 불일치")
    if any(len(v["content_hash"]) != 64 for v in reg["versions"]):
        failures.append("프롬프트 content hash 길이 오류")
    expect = {"total_queries": 10, "injection_blocked": 2, "pii_queries": 2,
              "pii_tokens_masked": 3, "retrieved": 8, "grounded": 7,
              "insufficient_grounding": 1}
    for k, want in expect.items():
        if rr[k] != want:
            failures.append(f"{k} {rr[k]}≠{want}")
    if not audit["all_passed"]:
        failures.append(f"위험 체크리스트 {audit['passed']}/{audit['total']}")
    if ap["decision"] != "APPROVED" or ap["hash_before"] == ap["hash_after"]:
        failures.append("승인 기록 불변식 위반")
    # 생성 허용 질의는 전부 출처 보유
    if any(not q["cited_sources"] for q in rr["query_log"]
           if q["decision"] == "ALLOW_GENERATION"):
        failures.append("생성 허용 질의에 출처 없음")

    print("CH14_RUN_PASS" if not failures else f"CH14_RUN_FAIL({'; '.join(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
