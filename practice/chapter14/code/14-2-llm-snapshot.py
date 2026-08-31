#!/usr/bin/env python3
"""실습 15.1 보강: 실제 LLM 생성 멀티벤더 스냅샷(비결정 — 재현 게이트 밖).

결정적 코어(14-1)가 "어느 조문이 근거인가"와 "생성해도 되는가"를 정한다.
이 스크립트는 그 판정을 신뢰해, **동일한 결정적 코어(프롬프트 v2·검색 결과·근거 조문)**를
서로 다른 두 제공자에게 그대로 넣어 생성시킨다 — 프롬프트·검색·근거 추적을 제공자에
독립적으로 두면 제공자를 갈아끼울 수 있다는 이 장의 설계를 실측으로 증명한다.

  제공자 1: 네이버 CLOVA Studio(HyperCLOVA X)   — CLOVA_STUDIO_API_KEY
  제공자 2: OpenAI Chat Completions              — OPENAI_API_KEY

원칙
  - 출력은 확률적 문장이라 재실행 바이트 동일을 보장하지 않는다 → "비결정 스냅샷"으로 표기.
  - 이 파일은 run_chapter14.py(PASS 게이트)에 포함되지 않는다(키 없이 오프라인 통과 보장).
  - API 키는 환경변수에서만 읽는다(평문 커밋 금지). 키·환경변수 이름을 출력에 남기지 않는다.
  - 한 제공자가 실패해도(키·요금제·장애) 정직히 기록하고, 다른 제공자 결과는 남긴다(우회 금지).

실행: cd practice/chapter14 && \
      CLOVA_STUDIO_API_KEY=... OPENAI_API_KEY=... venv/bin/python code/14-2-llm-snapshot.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INPUT = BASE / "data" / "input"
OUTPUT = BASE / "data" / "output"
REPORT = OUTPUT / "ch14_llmops_report.json"
SNAPSHOT = OUTPUT / "ch14_llm_snapshot.json"

# .env에서 로드할 화이트리스트 — 정확한 변수명만(무관한 비밀은 흡수하지 않는다, codex 규약).
# 접두 매칭이 아니라 정확 매칭이라 같은 접두어 아래 다른 비밀도 흡수하지 않는다.
ENV_WHITELIST_EXACT = {
    "CLOVA_STUDIO_API_KEY", "CLOVA_STUDIO_MODEL", "CLOVA_STUDIO_BASE_URL",
    "OPENAI_API_KEY", "OPENAI_MODEL",
}


def load_provider_env_from_dotenv() -> None:
    """저장소 루트 .env에서 제공자 키(정확 변수명 화이트리스트)만 골라 환경에 로드한다(값 출력 금지).

    .env 전체를 흡수하면 무관한 평문 비밀까지 프로세스 환경에 들어오므로,
    ENV_WHITELIST_EXACT에 명시된 다섯 변수만 정확 매칭으로 읽는다.
    호출자가 이미 환경변수로 주입했다면 그 값을 우선한다(setdefault).
    """
    dotenv = BASE.parent.parent / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text("utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() in ENV_WHITELIST_EXACT:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def call_clova(system: str, user: str, cfg: dict) -> dict:
    url = cfg["base_url"].rstrip("/") + f"/v3/chat-completions/{cfg['model']}"
    body = json.dumps({
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.0, "topP": 0.8, "topK": 0,
        "maxTokens": 256, "repeatPenalty": 1.1,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return {"answer": d["result"]["message"]["content"].strip(),
            "finish_reason": d["result"].get("finishReason")}


def call_openai(system: str, user: str, cfg: dict) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.0, "max_tokens": 256,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    ch = d["choices"][0]
    return {"answer": ch["message"]["content"].strip(),
            "finish_reason": ch.get("finish_reason")}


def build_context(cited_ids: list[str], doc_index: dict) -> str:
    if not cited_ids:
        return "(제공된 근거 문서 없음)"
    blocks = []
    for did in cited_ids:
        d = doc_index[did]
        blocks.append(f"[{d['article_no']} {d['title']}]\n{d['text']}")
    return "\n\n".join(blocks)


def run_provider(cfg: dict, targets: list[str], log: dict, qtext: dict,
                 doc_index: dict, system_text: str) -> list[dict]:
    results = []
    for qid in targets:
        q = log[qid]
        cited = q["cited_sources"]
        context = build_context(cited, doc_index)
        user = f"다음 근거 문서를 참고하여 질문에 답하라.\n\n{context}\n\n질문: {qtext[qid]}"
        try:
            out = cfg["call"](system_text, user, cfg)
        except urllib.error.HTTPError as e:  # noqa: PERF203 — 제공자별 정직한 실패 기록
            detail = ""
            try:
                detail = json.loads(e.read())["error"].get("code") or ""
            except Exception:  # noqa: BLE001
                detail = ""
            out = {"answer": None, "finish_reason": None,
                   "error": f"HTTP {e.code}{(' ' + detail) if detail else ''}"}
        except Exception as e:  # noqa: BLE001 — 우회 금지, 정확한 에러 기록
            out = {"answer": None, "finish_reason": None,
                   "error": f"{type(e).__name__}: {str(e)[:120]}"}
        results.append({
            "qid": qid, "category": q["category"], "decision": q["decision"],
            "provided_sources": cited, "grounding_provided": bool(cited),
            "answer": out["answer"], "finish_reason": out.get("finish_reason"),
            "error": out.get("error"),
        })
        tag = "생성" if cited else "근거없음(거절 관찰)"
        shown = (out["answer"] or out.get("error") or "")[:64].replace("\n", " ")
        print(f"  [{cfg['name']}·{qid}·{tag}] {shown}")
    return results


def main() -> int:
    if not REPORT.exists():
        print("증거 없음 — run_chapter14.py 먼저 실행", file=sys.stderr)
        return 2
    load_provider_env_from_dotenv()

    report = json.loads(REPORT.read_text("utf-8"))
    corpus = json.loads((INPUT / "corpus_pipa.json").read_text("utf-8"))
    doc_index = {d["doc_id"]: d for d in corpus["documents"]}
    active = next(v for v in report["prompt_registry"]["versions"]
                  if v["version"] == report["prompt_registry"]["active_version"])

    # 활성 프롬프트 원문·질의 텍스트는 결정적 코어(14-1)의 상수를 임포트해 재현한다.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "prompt_registry", BASE / "code" / "14-1-prompt-registry.py")
    pr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pr)
    system_text = pr.PROMPT_V2
    qtext = {qid: text for qid, _cat, text in pr.QUERIES}
    log = {q["qid"]: q for q in report["retrieval_and_risk"]["query_log"]}
    targets = report["generation"]["eligible_queries"] + ["Q6"]  # +근거부족 거절 관찰

    # 제공자 구성 — 키가 있는 제공자만 실행(무관 비밀 흡수 없음, 이름/값 미출력)
    providers = []
    if os.environ.get("CLOVA_STUDIO_API_KEY", "").strip():
        providers.append({
            "name": "NAVER CLOVA Studio", "call": call_clova,
            "model": os.environ.get("CLOVA_STUDIO_MODEL", "HCX-DASH-002").strip(),
            "base_url": os.environ.get("CLOVA_STUDIO_BASE_URL",
                                       "https://clovastudio.stream.ntruss.com").strip(),
            "key": os.environ["CLOVA_STUDIO_API_KEY"].strip(),
        })
    if os.environ.get("OPENAI_API_KEY", "").strip():
        providers.append({
            "name": "OpenAI", "call": call_openai,
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
            "key": os.environ["OPENAI_API_KEY"].strip(),
        })
    if not providers:
        print("제공자 키 없음(CLOVA_STUDIO_API_KEY/OPENAI_API_KEY) — 스냅샷 생성 불가"
              " (결정적 코어는 영향 없음)", file=sys.stderr)
        return 3

    provider_blocks = []
    for cfg in providers:
        print(f"=== {cfg['name']} ({cfg['model']}, temp=0) ===")
        results = run_provider(cfg, targets, log, qtext, doc_index, system_text)
        ok = sum(1 for r in results if r["answer"])
        err = sum(1 for r in results if r["error"])
        provider_blocks.append({
            "provider": cfg["name"], "model": cfg["model"], "temperature": 0.0,
            "generated": ok, "failed": err, "results": results,
        })

    snapshot = {
        "kind": "비결정 스냅샷(재현 게이트 밖) — 멀티벤더 LLM 생성 결과",
        "active_prompt_version": report["prompt_registry"]["active_version"],
        "active_prompt_hash8": active["hash8"],
        "note": ("동일한 결정적 코어(프롬프트 v2·검색·근거 조문)를 두 제공자에 그대로 넣어 실행했다. "
                 "temperature=0이라도 제공자 인프라 변화로 완전 재현은 보장되지 않으며, "
                 "제공자 가용성(키·요금제·장애)도 실행 시점에 따라 달라진다 → 재현 게이트 밖. "
                 "결정적 코어(근거·생성 허용 여부)는 ch14_llmops_report.json에 있다(12장 지연 스냅샷 선례)."),
        "providers": provider_blocks,
    }
    SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", "utf-8")
    summary = ", ".join(f"{p['provider']} {p['model']}(생성 {p['generated']}/실패 {p['failed']})"
                        for p in provider_blocks)
    print(f"스냅샷 저장: {SNAPSHOT} — {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
