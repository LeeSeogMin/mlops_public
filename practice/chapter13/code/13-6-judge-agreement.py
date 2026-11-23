#!/usr/bin/env python3
"""13주차 보강: 규칙 검사·LLM 채점과 기준 라벨의 일치도(결정적).

입력은 커밋된 세 파일뿐이다 — 규칙 검사 결과(ch13_output_check.json), LLM 채점 결과(ch13_llm_judge.json),
기준 라벨(data/input/ch13_claim_labels.json). 그래서 재실행해도 같은 값이 나온다.

  일치율  = 판정이 같은 주장 수 / 전체 주장 수
  코헨 카파 = (일치율 - 우연 일치율) / (1 - 우연 일치율)
            우연 일치율은 두 판정자가 각 판정을 내린 비율을 곱해 더한 값이다.
  놓침    = 기준 라벨이 NOT_SUPPORTED인데 SUPPORTED로 판정한 주장
  오탐    = 기준 라벨이 SUPPORTED인데 NOT_SUPPORTED로 판정한 주장

기준 라벨은 사람 검토를 거치지 않은 초안이다(라벨 파일의 status 필드). 일치도는 "초안 라벨 대비"로 읽는다.

실행: cd practice/chapter13 && python code/13-6-judge-agreement.py
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CHECK = BASE / "data" / "output" / "ch13_output_check.json"
JUDGE = BASE / "data" / "output" / "ch13_llm_judge.json"
LABELS = BASE / "data" / "input" / "ch13_claim_labels.json"
OUT = BASE / "data" / "output" / "ch13_judge_agreement.json"

# 규칙 검사의 판정을 두 값으로 묶는다
RULE_TO_BINARY = {"SUPPORTED": "SUPPORTED", "SUPPORTED_UNCITED": "SUPPORTED",
                  "UNSUPPORTED": "NOT_SUPPORTED", "UNSUPPORTED_UNCITED": "NOT_SUPPORTED",
                  "CITATION_INVALID": "NOT_SUPPORTED"}


def agreement(pred: dict, gold: dict) -> dict:
    ids = sorted(gold)
    n = len(ids)
    same = sum(1 for i in ids if pred[i] == gold[i])
    po = same / n
    pe = sum((sum(1 for i in ids if pred[i] == c) / n) * (sum(1 for i in ids if gold[i] == c) / n)
             for c in ("SUPPORTED", "NOT_SUPPORTED"))
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return {"n": n, "agree": same, "agreement_rate": round(po, 3), "cohen_kappa": round(kappa, 3),
            "missed": [i for i in ids if gold[i] == "NOT_SUPPORTED" and pred[i] == "SUPPORTED"],
            "false_alarm": [i for i in ids if gold[i] == "SUPPORTED" and pred[i] == "NOT_SUPPORTED"]}


def main() -> int:
    labels = json.loads(LABELS.read_text("utf-8"))
    gold = {x["claim_id"]: x["label"] for x in labels["labels"]}

    check = json.loads(CHECK.read_text("utf-8"))
    clova = next(p for p in check["providers"] if p["provider"] == "NAVER CLOVA Studio")
    rule = {f"{a['qid']}-c{i}": RULE_TO_BINARY[c["verdict"]]
            for a in clova["answers"] for i, c in enumerate(a["claims"])
            if c["verdict"] != "FRAMING"}

    raters = {"규칙 검사(13-3)": rule}
    for j in json.loads(JUDGE.read_text("utf-8"))["judges"]:
        raters[f"LLM 채점 {j['judge_model']}"] = {v["claim_id"]: v["verdict"] for v in j["verdicts"]}

    print(f"기준 라벨: {labels['status'].split(':')[0]} — 주장 {len(gold)}건, "
          f"NOT_SUPPORTED {sum(1 for v in gold.values() if v == 'NOT_SUPPORTED')}건")
    result = {"label_status": labels["status"], "raters": {}}
    for name, pred in raters.items():
        a = agreement(pred, gold)
        result["raters"][name] = a
        print(f"=== {name} ===")
        print(f"  일치 {a['agree']}/{a['n']} (일치율 {a['agreement_rate']}), 코헨 카파 {a['cohen_kappa']}")
        print(f"  놓침 {a['missed']}")
        print(f"  오탐 {a['false_alarm']}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
