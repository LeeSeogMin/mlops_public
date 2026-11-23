#!/usr/bin/env python3
"""13주차 보강: LLM 채점(LLM-as-a-judge) — 비결정, 재현 게이트 밖.

13-3의 규칙 검사는 낱말이 원문에 있는지만 세므로, 조건을 빼서 범위를 넓힌 주장(Q1의 제15조 제3항)을
통과시켰다. 이 스크립트는 같은 주장 25건(FRAMING 제외)을 다른 회사의 LLM에게 넘겨
"넘겨준 조문으로 뒷받침되는가"를 판정하게 하고, 결과를 ch13_llm_judge.json에 남긴다.

  - 채점 기준은 기준 라벨 파일(data/input/ch13_claim_labels.json)의 guideline과 같은 문장을 쓴다.
  - 생성 모델(CLOVA)과 다른 제공자의 모델 두 개로 채점한다 — 채점 모델에 따라 결과가 달라지는지 본다.
  - 채점 결과와 기준 라벨의 일치도는 13-6이 결정적으로 계산한다.

실행: cd practice/chapter13 && python code/13-5-llm-judge.py   (OPENAI_API_KEY 필요)
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
CHECK = OUTPUT / "ch13_output_check.json"
LABELS = INPUT / "ch13_claim_labels.json"
OUT = OUTPUT / "ch13_llm_judge.json"

JUDGES = ["gpt-5.2-2025-12-11", "gpt-4o-mini"]

SYSTEM = (
    "너는 법령 질의응답 서비스의 답변을 검수하는 채점자다. "
    "주어진 '근거 조문'만을 기준으로 '주장'을 판정한다. 근거 조문 밖의 지식은 쓰지 않는다.\n"
    "판정 기준:\n{guideline}\n"
    '출력은 JSON 하나만: {{"verdict": "SUPPORTED" 또는 "NOT_SUPPORTED", "reason": "한 문장"}}'
)


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, BASE / "code" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def judge(model: str, key: str, system: str, user: str) -> dict:
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    body["max_completion_tokens"] = 300
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    out = json.loads(d["choices"][0]["message"]["content"])
    usage = d.get("usage") or {}
    return {"verdict": out.get("verdict"), "reason": out.get("reason"),
            "response_model": d.get("model"),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}


def main() -> int:
    snap = _load("llm_snapshot", "13-2-llm-snapshot.py")
    snap.load_provider_env_from_dotenv()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        print("OPENAI_API_KEY 없음 — 채점 불가", file=sys.stderr)
        return 3
    check = json.loads(CHECK.read_text("utf-8"))
    labels = json.loads(LABELS.read_text("utf-8"))
    corpus = json.loads((INPUT / "corpus_pipa.json").read_text("utf-8"))
    doc_index = {d["doc_id"]: d for d in corpus["documents"]}
    system = SYSTEM.format(guideline="\n".join(f"- {g}" for g in labels["guideline"]))

    clova = next(p for p in check["providers"] if p["provider"] == "NAVER CLOVA Studio")
    items = []
    for a in clova["answers"]:
        for i, c in enumerate(a["claims"]):
            if c["verdict"] == "FRAMING":
                continue
            items.append({"claim_id": f"{a['qid']}-c{i}", "claim": c["claim"],
                          "sources": a["provided_sources"]})

    results = []
    for model in JUDGES:
        print(f"=== 채점 모델 {model} (temperature=0) ===")
        verdicts = []
        for it in items:
            context = "\n\n".join(f"[{doc_index[s]['article_no']}]\n{doc_index[s]['text']}"
                                  for s in it["sources"])
            user = f"근거 조문:\n{context}\n\n주장:\n{it['claim']}"
            try:
                v = judge(model, key, system, user)
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as e:
                v = {"verdict": None, "reason": None, "error": type(e).__name__}
            verdicts.append({"claim_id": it["claim_id"], **v})
            print(f"  {it['claim_id']:6} {v['verdict']}")
        results.append({"judge_model": model, "verdicts": verdicts,
                        "input_tokens_total": sum(v.get("input_tokens") or 0 for v in verdicts),
                        "output_tokens_total": sum(v.get("output_tokens") or 0 for v in verdicts)})

    OUT.write_text(json.dumps({
        "kind": "비결정 스냅샷(재현 게이트 밖) — LLM 채점 결과",
        "target": "ch13_output_check.json의 NAVER CLOVA Studio 주장 25건",
        "system_prompt": system,
        "judges": results,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"저장: {OUT.relative_to(BASE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
