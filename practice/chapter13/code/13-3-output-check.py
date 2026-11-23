#!/usr/bin/env python3
"""13주차 보강: 출력 쪽 근거 검증 + 추적 기록(OpenTelemetry GenAI 속성 이름).

입력 쪽 세 게이트(13-1)는 "근거가 있는가"까지만 판정한다. 이 스크립트는 그 뒤,
**실제로 생성된 답변 문장이 넘겨준 조문으로 뒷받침되는가**를 규칙으로 검사한다.

  1. 답변을 주장(claim) 단위로 나눈다 — 줄과 문장 끝을 기준으로 자른다.
  2. 주장 끝의 괄호 인용 "(제N조 M항 K호)"를 읽어
     (a) 인용 조문이 실제로 넘겨준 근거(provided_sources)에 있는가
     (b) 인용한 항(①·M항)이 그 조문에 실제로 있는가
     (c) 주장의 내용어가 인용 단위(항 또는 조문) 본문에 몇 % 나오는가(내용어 재현율)
     를 판정한다.
  3. 답변 단위로 PASS / FLAG를 정한다. FLAG는 사람 검토로 보낸다.

입력은 커밋된 스냅샷(data/output/ch13_llm_snapshot.json)과 코퍼스뿐이므로,
생성 자체는 비결정이어도 **이 검사는 재실행해도 같은 값**을 낸다.

같은 실행에서 질의별 추적 기록을 OpenTelemetry GenAI 의미 규약의 속성 이름으로 남긴다
(semantic-conventions-genai v0.1.0, 상태 Development — 이름이 바뀔 수 있다).

실행: cd practice/chapter13 && python code/13-3-output-check.py
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INPUT = BASE / "data" / "input"
OUTPUT = BASE / "data" / "output"
REPORT = OUTPUT / "ch13_llmops_report.json"
SNAPSHOT = OUTPUT / "ch13_llm_snapshot.json"

# 주장 하나가 "뒷받침됨"이려면 내용어의 절반 이상이 인용 단위 본문에 나와야 한다.
# 이 장에서 정한 값이며 사람 라벨로 보정한 값이 아니다.
SUPPORT_THRESHOLD = 0.5
REFUSAL_MARK = "답변할 수 없습니다"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
# 답변 문장에서 내용어로 세지 않는 말: 서술어 어미·지시어·접속어. 질의용 STOPWORDS(13-1)와 별도다.
ANSWER_FUNCTION_WORDS = {"있습니다", "합니다", "있을", "있다", "해야", "하며", "수도", "또한",
                         "다만", "이는", "이러한", "이에", "대한", "대해", "통해", "해당", "가지"}
CITE_RE = re.compile(r"\(([^()]*제\d+조[^()]*)\)")
FRAMING_RE = re.compile(r"(다음과 같습니다|다음과 같다)[.:：]?$")

# OpenTelemetry GenAI가 값을 정해 둔 제공자는 그 값을 쓰고, 정해 두지 않은 제공자는 소문자 이름을 쓴다.
OTEL_PROVIDER = {"OpenAI": "openai", "NAVER CLOVA Studio": "naver.clova_studio"}


def _load_core():
    spec = importlib.util.spec_from_file_location(
        "prompt_registry", BASE / "code" / "13-1-prompt-registry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def split_claims(answer: str) -> list[str]:
    """답변을 주장 단위로 자른다. 괄호 인용만 남은 조각은 앞 주장에 붙인다."""
    pieces: list[str] = []
    for line in answer.splitlines():
        line = line.strip()
        if not line:
            continue
        # 문장 끝(다./요./). 뒤)에서 자른다. "1. "처럼 숫자 뒤 마침표는 자르지 않는다.
        for s in re.split(r"(?<=[다요]\.)\s*|(?<=\)\.)\s*", line):
            s = s.strip()
            if not s:
                continue
            # 문장 앞에 붙은 괄호 인용은 앞 문장의 인용이다 — "…있습니다.(제21조 ①) 다만, …"
            lead = re.match(r"\([^()]*제\d+조[^()]*\)\.?\s*", s)
            if pieces and lead:
                pieces[-1] = pieces[-1] + " " + lead.group(0).strip()
                s = s[lead.end():].strip()
                if not s:
                    continue
            pieces.append(s)
    return pieces


def parse_citations(claim: str) -> list[dict]:
    """괄호 안의 "제N조 M항 K호", "제N조 ②, ④" 꼴을 읽어 (조, 항 목록, 호)로 돌려준다."""
    out = []
    for group in CITE_RE.findall(claim):
        for m in re.finditer(r"제(\d+)조([^제]*)", group):
            art, rest = m.group(1), m.group(2)
            paras = [int(p) for p in re.findall(r"(\d+)\s*항", rest)]
            paras += [CIRCLED.index(c) + 1 for c in rest if c in CIRCLED]
            item = re.search(r"(\d+)\s*호", rest)
            out.append({"article": art, "paragraphs": sorted(set(paras)),
                        "item": int(item.group(1)) if item else None})
    return out


def paragraph_text(article_text: str, no: int) -> str | None:
    """조문 본문에서 no번째 항(①…)을 잘라 낸다. 항 표시가 없는 조문은 1항=전문으로 본다."""
    mark = CIRCLED[no - 1]
    if mark not in article_text:
        return article_text if no == 1 and CIRCLED[0] not in article_text else None
    start = article_text.index(mark)
    nxt = CIRCLED[no] if no < len(CIRCLED) else None
    end = article_text.index(nxt) if nxt and nxt in article_text else len(article_text)
    return article_text[start:end]


def check_claim(claim: str, provided: list[str], doc_index: dict, keywords) -> dict:
    body = CITE_RE.sub("", claim)
    kws = [k for k in keywords(body) if k not in ANSWER_FUNCTION_WORDS]
    cites = parse_citations(claim)
    provided_texts = [doc_index[d]["text"] for d in provided]

    if not cites:
        if FRAMING_RE.search(body.strip()):
            return {"claim": claim, "verdict": "FRAMING", "citations": []}
        hits = [k for k in kws if any(k in t for t in provided_texts)]
        recall = round(len(hits) / len(kws), 3) if kws else 0.0
        verdict = "SUPPORTED_UNCITED" if recall >= SUPPORT_THRESHOLD else "UNSUPPORTED_UNCITED"
        return {"claim": claim, "verdict": verdict, "citations": [],
                "keyword_recall": recall, "missing_keywords": [k for k in kws if k not in hits]}

    units, problems = [], []
    for c in cites:
        doc_id = f"pipa-art{c['article']}"
        if doc_id not in provided:
            problems.append(f"제{c['article']}조는 넘겨준 근거에 없음")
            continue
        text = doc_index[doc_id]["text"]
        if not c["paragraphs"]:
            units.append(text)
            continue
        for p in c["paragraphs"]:
            pt = paragraph_text(text, p)
            if pt is None:
                problems.append(f"제{c['article']}조 제{p}항 없음")
            else:
                units.append(pt)
    unit_text = "\n".join(units)
    hits = [k for k in kws if k in unit_text]
    recall = round(len(hits) / len(kws), 3) if kws else 0.0
    if problems:
        verdict = "CITATION_INVALID"
    elif recall >= SUPPORT_THRESHOLD:
        verdict = "SUPPORTED"
    else:
        verdict = "UNSUPPORTED"
    return {"claim": claim, "verdict": verdict, "citations": cites,
            "keyword_recall": recall, "missing_keywords": [k for k in kws if k not in hits],
            "citation_problems": problems}


def check_answer(r: dict, doc_index: dict, keywords) -> dict:
    base = {"qid": r["qid"], "gate_decision": r["decision"],
            "provided_sources": r["provided_sources"], "finish_reason": r["finish_reason"]}
    if not r["answer"]:
        return {**base, "answer_verdict": "NO_OUTPUT", "error": r.get("error"), "claims": []}
    if REFUSAL_MARK in r["answer"]:
        return {**base, "answer_verdict": "REFUSAL", "claims": []}
    claims = [check_claim(c, r["provided_sources"], doc_index, keywords)
              for c in split_claims(r["answer"])]
    bad = [c for c in claims if c["verdict"] in
           ("UNSUPPORTED", "CITATION_INVALID", "UNSUPPORTED_UNCITED")]
    reasons = []
    if r["finish_reason"] == "length":
        reasons.append("TRUNCATED")
    if bad:
        reasons.append(f"주장 {len(bad)}건 근거 미확인")
    return {**base, "answer_verdict": "FLAG" if reasons else "PASS",
            "flag_reasons": reasons, "claims": claims}


def trace_spans(report: dict, snapshot: dict) -> list[dict]:
    """질의 하나를 검색 span 하나 + 제공자별 추론 span으로 기록한다(OTel GenAI 속성 이름)."""
    corpus_id = report["corpus"]["corpus_id"]
    hash8 = snapshot["active_prompt_hash8"]
    by_qid = {q["qid"]: q for q in report["retrieval_and_risk"]["query_log"]}
    spans = []
    for qid, q in by_qid.items():
        trace = {"qid": qid, "spans": []}
        if q["top_doc"] is not None:
            trace["spans"].append({
                "name": "retrieval", "kind": "INTERNAL",
                "attributes": {
                    "gen_ai.operation.name": "retrieval",
                    "gen_ai.data_source.id": corpus_id,
                    "gen_ai.retrieval.top_k": 2,
                    "gen_ai.retrieval.documents": [
                        {"id": d, "score": s} for d, s in q["top_ranked"][:2]],
                    "app.gate.decision": q["decision"],
                }})
        for p in snapshot["providers"]:
            r = next((x for x in p["results"] if x["qid"] == qid), None)
            if r is None:
                continue
            attrs = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": OTEL_PROVIDER.get(p["provider"], p["provider"].lower()),
                "gen_ai.request.model": p["model"],
                "gen_ai.request.temperature": p["temperature"],
                "gen_ai.request.max_tokens": 256,
                "gen_ai.response.finish_reasons": [r["finish_reason"] or "error"],
                # 스냅샷 스키마(13-2)에 토큰 사용량 필드가 없어 비워 둔다 — 비용을 산출할 수 없다.
                "gen_ai.usage.input_tokens": r.get("usage_input_tokens"),
                "gen_ai.usage.output_tokens": r.get("usage_output_tokens"),
                "app.prompt.hash8": hash8,
                "app.provided_sources": r["provided_sources"],
            }
            if r.get("error"):
                attrs["error.type"] = r["error"]
            trace["spans"].append({"name": f"chat {p['model']}", "kind": "CLIENT",
                                   "attributes": attrs})
        spans.append(trace)
    return spans


def build(output_dir: Path = OUTPUT) -> dict:
    core = _load_core()
    report = json.loads(REPORT.read_text("utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text("utf-8"))
    corpus = json.loads((INPUT / "corpus_pipa.json").read_text("utf-8"))
    doc_index = {d["doc_id"]: d for d in corpus["documents"]}

    providers = []
    for p in snapshot["providers"]:
        answers = [check_answer(r, doc_index, core.keywords) for r in p["results"]]
        count = {}
        for a in answers:
            count[a["answer_verdict"]] = count.get(a["answer_verdict"], 0) + 1
        claims = [c for a in answers for c in a["claims"]]
        ccount = {}
        for c in claims:
            ccount[c["verdict"]] = ccount.get(c["verdict"], 0) + 1
        providers.append({"provider": p["provider"], "model": p["model"],
                          "answer_verdicts": dict(sorted(count.items())),
                          "claim_verdicts": dict(sorted(ccount.items())),
                          "claims_total": len(claims), "answers": answers})

    gate_allowed = set(report["generation"]["eligible_queries"])
    gate_vs_model = [a["qid"] for p in providers for a in p["answers"]
                     if a["qid"] in gate_allowed and a["answer_verdict"] == "REFUSAL"]
    result = {
        "kind": "출력 쪽 근거 검증(결정적 — 커밋된 스냅샷을 입력으로 함)",
        "support_threshold": SUPPORT_THRESHOLD,
        "snapshot_prompt_hash8": snapshot["active_prompt_hash8"],
        "providers": providers,
        "gate_allowed_but_model_refused": gate_vs_model,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ch13_output_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    spans = {
        "convention": "OpenTelemetry semantic-conventions-genai v0.1.0 (status: Development)",
        "traces": trace_spans(report, snapshot),
    }
    (output_dir / "ch13_trace_spans.json").write_text(
        json.dumps(spans, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return result


def main() -> int:
    if not REPORT.exists() or not SNAPSHOT.exists():
        print("증거 없음 — run_chapter13.py와 스냅샷 파일이 먼저 있어야 함")
        return 2
    res = build()
    for p in res["providers"]:
        print(f"=== 출력 검증: {p['provider']} {p['model']} ===")
        print(f"  답변 판정 {p['answer_verdicts']}")
        print(f"  주장 {p['claims_total']}건 판정 {p['claim_verdicts']}")
        for a in p["answers"]:
            if a["answer_verdict"] == "FLAG":
                print(f"  {a['qid']} FLAG {a['flag_reasons']}")
                for c in a["claims"]:
                    if c["verdict"] not in ("SUPPORTED", "SUPPORTED_UNCITED", "FRAMING"):
                        print(f"    - {c['verdict']} 재현율 {c.get('keyword_recall')}"
                              f" 빠진 내용어 {c.get('missing_keywords')}")
    print(f"  게이트 허용 후 모델 거절: {res['gate_allowed_but_model_refused']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
