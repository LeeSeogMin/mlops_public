#!/usr/bin/env python3
"""13주차 보강: 토큰 사용량을 기록하는 생성 스냅샷(비결정 — 재현 게이트 밖).

13-2가 남긴 스냅샷(ch13_llm_snapshot.json)은 토큰 사용량을 저장하지 않아 비용을 산출할 수 없었다.
이 스크립트는 같은 결정적 코어(프롬프트 v2·근거 조문·질의 8건)를 같은 두 모델에 다시 넣고,
호출마다 OpenTelemetry GenAI 속성 이름으로 사용량·응답 모델·종료 사유를 기록한다.

  - 기존 스냅샷은 원고가 인용하므로 덮어쓰지 않는다 → ch13_llm_snapshot_usage.json에 따로 저장한다.
  - 모델은 기존 스냅샷과 같게 고정한다(.env의 *_MODEL 값을 쓰지 않는다).
  - 새 답변에도 13-3의 출력 검증을 그대로 적용해 판정을 함께 남긴다.
  - 비용은 제공자가 공개한 단가가 확인된 모델만 계산한다.
  - 질의는 게이트 2가 마스킹한 문장(masked_query)을 넘긴다. 13-2는 원문 질의(QUERIES)를 넘겨
    합성 주민등록번호가 제공자에게 전달됐다 — 마스킹을 검색·로그에만 적용하고 생성 호출에는
    적용하지 않은 누락이다.

실행: cd practice/chapter13 && python code/13-4-usage-snapshot.py   (CLOVA_STUDIO_API_KEY·OPENAI_API_KEY 필요)
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INPUT = BASE / "data" / "input"
OUTPUT = BASE / "data" / "output"
REPORT = OUTPUT / "ch13_llmops_report.json"
OUT = OUTPUT / "ch13_llm_snapshot_usage.json"

MAX_TOKENS = 256  # 13-2와 같은 값
# 100만 토큰당 달러. OpenAI 모델 문서의 gpt-4o-mini 단가(입력 0.15, 출력 0.60).
# CLOVA Studio는 요금표의 금액을 확인하지 못해 비워 둔다(None이면 비용을 계산하지 않는다).
PRICE_PER_1M_USD = {"gpt-4o-mini": (0.15, 0.60), "HCX-DASH-002": None}


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, BASE / "code" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _post(url: str, body: dict, key: str) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def call_clova(system: str, user: str, model: str, key: str, base_url: str) -> dict:
    d = _post(base_url.rstrip("/") + f"/v3/chat-completions/{model}", {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0, "topP": 0.8, "topK": 0, "maxTokens": MAX_TOKENS, "repeatPenalty": 1.1,
    }, key)
    res = d["result"]
    usage = res.get("usage") or {}
    return {"answer": res["message"]["content"].strip(), "finish_reason": res.get("finishReason"),
            "response_model": model,  # CLOVA 응답에는 모델 이름 필드가 없다
            "input_tokens": usage.get("promptTokens"), "output_tokens": usage.get("completionTokens")}


def call_openai(system: str, user: str, model: str, key: str, base_url: str) -> dict:
    d = _post("https://api.openai.com/v1/chat/completions", {
        "model": model, "temperature": 0.0, "max_tokens": MAX_TOKENS,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }, key)
    ch = d["choices"][0]
    usage = d.get("usage") or {}
    return {"answer": ch["message"]["content"].strip(), "finish_reason": ch.get("finish_reason"),
            "response_model": d.get("model"),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}


PROVIDERS = [
    {"name": "NAVER CLOVA Studio", "otel": "naver.clova_studio", "model": "HCX-DASH-002",
     "key_env": "CLOVA_STUDIO_API_KEY", "call": call_clova},
    {"name": "OpenAI", "otel": "openai", "model": "gpt-4o-mini",
     "key_env": "OPENAI_API_KEY", "call": call_openai},
]


def main() -> int:
    if not REPORT.exists():
        print("증거 없음 — run_chapter13.py 먼저 실행", file=sys.stderr)
        return 2
    snap = _load("llm_snapshot", "13-2-llm-snapshot.py")
    core = _load("prompt_registry", "13-1-prompt-registry.py")
    check = _load("output_check", "13-3-output-check.py")
    snap.load_provider_env_from_dotenv()

    report = json.loads(REPORT.read_text("utf-8"))
    corpus = json.loads((INPUT / "corpus_pipa.json").read_text("utf-8"))
    doc_index = {d["doc_id"]: d for d in corpus["documents"]}
    log = {q["qid"]: q for q in report["retrieval_and_risk"]["query_log"]}
    targets = report["generation"]["eligible_queries"] + ["Q6"]  # 13-2와 같은 8건
    base_url = os.environ.get("CLOVA_STUDIO_BASE_URL", "https://clovastudio.stream.ntruss.com").strip()

    blocks = []
    for p in PROVIDERS:
        key = os.environ.get(p["key_env"], "").strip()
        if not key:
            print(f"{p['name']} 키 없음 — 건너뜀", file=sys.stderr)
            continue
        print(f"=== {p['name']} ({p['model']}, temp=0, max_tokens={MAX_TOKENS}) ===")
        calls = []
        for qid in targets:
            cited = log[qid]["cited_sources"]
            user = ("다음 근거 문서를 참고하여 질문에 답하라.\n\n"
                    f"{snap.build_context(cited, doc_index)}\n\n질문: {log[qid]['masked_query']}")
            try:
                out = p["call"](core.PROMPT_V2, user, p["model"], key, base_url)
                err = None
            except urllib.error.HTTPError as e:
                out, err = {}, f"HTTP {e.code}"
            except Exception as e:  # noqa: BLE001 — 실패를 그대로 기록한다
                out, err = {}, type(e).__name__
            result = {"qid": qid, "decision": log[qid]["decision"], "provided_sources": cited,
                      "answer": out.get("answer"), "finish_reason": out.get("finish_reason")}
            verdict = check.check_answer(result, doc_index, core.keywords)
            attrs = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": p["otel"],
                "gen_ai.request.model": p["model"],
                "gen_ai.request.temperature": 0.0,
                "gen_ai.request.max_tokens": MAX_TOKENS,
                "gen_ai.response.model": out.get("response_model"),
                "gen_ai.response.finish_reasons": [out.get("finish_reason") or "error"],
                "gen_ai.usage.input_tokens": out.get("input_tokens"),
                "gen_ai.usage.output_tokens": out.get("output_tokens"),
            }
            if err:
                attrs["error.type"] = err
            calls.append({**result, "attributes": attrs,
                          "output_check": verdict["answer_verdict"],
                          "flag_reasons": verdict.get("flag_reasons", [])})
            print(f"  {qid} 입력 {attrs['gen_ai.usage.input_tokens']} 출력 "
                  f"{attrs['gen_ai.usage.output_tokens']} 종료 {attrs['gen_ai.response.finish_reasons'][0]}"
                  f" 출력검증 {verdict['answer_verdict']}")

        ok = [c for c in calls if c["attributes"]["gen_ai.usage.input_tokens"] is not None]
        tin = sum(c["attributes"]["gen_ai.usage.input_tokens"] for c in ok)
        tout = sum(c["attributes"]["gen_ai.usage.output_tokens"] for c in ok)
        price = PRICE_PER_1M_USD.get(p["model"])
        cost = round((tin * price[0] + tout * price[1]) / 1_000_000, 6) if price else None
        blocks.append({"provider": p["name"], "model": p["model"], "calls": calls,
                       "succeeded": len(ok), "failed": len(calls) - len(ok),
                       "input_tokens_total": tin, "output_tokens_total": tout,
                       "price_per_1m_usd": price, "cost_usd": cost})
        print(f"  합계 입력 {tin} / 출력 {tout} 토큰, 비용 "
              f"{'$' + format(cost, '.6f') if cost is not None else '단가 미확인'}")

    if not blocks:
        print("제공자 키 없음 — 스냅샷 생성 불가", file=sys.stderr)
        return 3
    OUT.write_text(json.dumps({
        "kind": "비결정 스냅샷(재현 게이트 밖) — 토큰 사용량 기록",
        "convention": "OpenTelemetry semantic-conventions-genai v0.1.0 (status: Development)",
        "active_prompt_hash8": next(v["hash8"] for v in report["prompt_registry"]["versions"]
                                    if v["version"] == report["prompt_registry"]["active_version"]),
        "providers": blocks,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"저장: {OUT.relative_to(BASE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
