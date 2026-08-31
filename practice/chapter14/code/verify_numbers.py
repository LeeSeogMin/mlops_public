#!/usr/bin/env python3
"""상세 원고(lecture/docs/chapter15.md) 핵심 수치 ↔ 결정적 증거 JSON 대조.

결정적 증거(ch14_llmops_report.json)에서 기대값을 읽어, 본문이 인용하는 핵심 수치가
(1) 증거와 일치하고 (2) 본문에 실제로 등장하는지 검사한다(맥락 고정 문구 포함). 모두 통과 시 ALL_PASS.

범위 한계(의도적):
  - LLM 생성 스냅샷(ch14_llm_snapshot.json)의 문장은 비결정이므로 대조 대상이 아니다.
    본문의 스냅샷 서술("이번 스냅샷에서 …")은 게이트 밖이며 여기서 검증하지 않는다.
  - 이 검증기는 결정적 코어의 핵심 지표·해시·대표 점수만 확인한다(모든 문장의 전수 검증 아님).

실행: cd practice/chapter14 && venv/bin/python code/verify_numbers.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPORT = BASE / "data" / "output" / "ch14_llmops_report.json"
DOCS = BASE.parent.parent / "lecture" / "docs" / "chapter15.md"


def main() -> int:
    if not REPORT.exists():
        print(f"증거 없음: {REPORT} — run_chapter14.py 먼저 실행", file=sys.stderr)
        return 2
    r = json.loads(REPORT.read_text("utf-8"))
    corpus = r["corpus"]
    reg = r["prompt_registry"]
    rr = r["retrieval_and_risk"]
    audit = r["risk_checklist"]
    log = {q["qid"]: q for q in rr["query_log"]}
    v1 = next(v for v in reg["versions"] if v["version"] == "v1")
    v2 = next(v for v in reg["versions"] if v["version"] == "v2")

    # (라벨, 증거값, 본문에 반드시 등장해야 하는 문자열) — 증거에서 유도
    checks = [
        ("코퍼스 조문 수", corpus["documents"], "7"),
        ("프롬프트 버전 수", len(reg["versions"]), "2"),
        ("총 질의 수", rr["total_queries"], "10"),
        ("인젝션 차단", rr["injection_blocked"], "2"),
        ("PII 질의", rr["pii_queries"], "2"),
        ("PII 마스킹 토큰", rr["pii_tokens_masked"], "3"),
        ("검색 수행", rr["retrieved"], "8"),
        ("근거 충분", rr["grounded"], "7"),
        ("근거 부족", rr["insufficient_grounding"], "1"),
        ("체크리스트 총수", audit["total"], "10"),
        ("체크리스트 통과", audit["passed"], "10"),
        ("v1 프롬프트 hash8", v1["hash8"], v1["hash8"]),
        ("v2 프롬프트 hash8", v2["hash8"], v2["hash8"]),
        ("Q1 BM25 상위 점수", log["Q1"]["top_score"], "26.1575"),
        ("Q3 BM25 상위 점수", log["Q3"]["top_score"], "27.9702"),
        ("Q5 BM25 상위 점수", log["Q5"]["top_score"], "30.827"),
        ("Q6 BM25 상위 점수(근거부족)", log["Q6"]["top_score"], "1.641"),
        ("코퍼스 무결성 해시8", corpus["content_hash8"], corpus["content_hash8"]),
    ]

    failures = []
    for label, evidence, token in checks:
        try:
            same = str(evidence) == token or float(evidence) == float(token)
        except (TypeError, ValueError):
            same = str(evidence) == token
        if not same:
            failures.append(f"[증거불일치] {label}: 증거 {evidence} ≠ 표기 {token}")

    # 핵심 주장은 맥락 고정 문구로 검사(맨숫자 토큰이 다른 곳에 있어도 통과하는 느슨함 방지)
    anchored = [
        "7조문",
        "인젝션 의심 2건",
        "근거 충분 7건",
        "근거 부족 1건",
        "마스킹 토큰 3건",
        "10/10",
        "10항목",
        v2["hash8"],           # 활성 프롬프트 content hash 앞 8자
        v1["hash8"],
        str(log["Q1"]["top_score"]),   # 26.1575
        str(log["Q6"]["top_score"]),   # 1.641 (근거 부족 워크드)
        corpus["content_hash8"],       # 코퍼스 무결성 해시(변조 탐지)
    ]

    if DOCS.exists():
        text = DOCS.read_text("utf-8")
        for label, _e, token in checks:
            if token not in text:
                failures.append(f"[본문누락] {label}: '{token}' 본문에 없음")
        for phrase in anchored:
            if phrase not in text:
                failures.append(f"[맥락누락] 고정 문구 '{phrase}' 본문에 없음")
    else:
        print(f"주의: {DOCS} 없음 — 증거 자기정합성만 검사")

    for f in failures:
        print(f)
    print(f"대조 {len(checks)}건, 실패 {len(failures)}건")
    print("ALL_PASS" if not failures else "VERIFY_FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
