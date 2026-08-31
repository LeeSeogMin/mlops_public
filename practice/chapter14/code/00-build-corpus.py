#!/usr/bin/env python3
"""RAG 코퍼스 생성(provenance) — 국가법령정보 공동활용 OPEN API에서 개인정보 보호법 조문을 받아
data/input/corpus_pipa.json으로 저장한다.

- 실재 공공 문서만 사용한다(하드룰): 조문 텍스트는 법제처 OPEN API의 원문이다.
- 이 스크립트는 코퍼스를 한 번 만들어 커밋하기 위한 provenance 도구다.
  실습 본체(14-1)는 네트워크 없이 이 커밋된 코퍼스를 읽어 결정적으로 동작한다.
- OC(기관코드)는 환경변수 LAW_OPEN_API_OC에서만 읽는다(평문 커밋 금지).

실행: LAW_OPEN_API_OC=... venv/bin/python code/00-build-corpus.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "input" / "corpus_pipa.json"

# 코퍼스에 담을 조문(공공 LLM 서비스가 시민 데이터를 다룰 때 직접 관련되는 핵심 조항)
WANT = ["3", "15", "18", "21", "23", "29", "35"]
MST = "270351"  # 개인정보 보호법 법령 마스터 번호(현행, 시행 2025-10-02)
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"
# 참고문헌·본문 인용용 사람이 보는 공식 페이지(https)
HUMAN_URL = "https://www.law.go.kr/법령/개인정보보호법"


def _flatten_article(art: dict) -> str:
    """조문내용 + 항 + 호를 사람이 읽는 한 덩어리 텍스트로 편다."""
    parts = [art.get("조문내용", "").strip()]
    hang = art.get("항")
    if isinstance(hang, dict):
        hang = [hang]
    for h in hang or []:
        htext = (h.get("항내용") or "").strip()
        if htext:
            parts.append(htext)
        ho = h.get("호")
        if isinstance(ho, dict):
            ho = [ho]
        for x in ho or []:
            xtext = (x.get("호내용") or "").strip()
            if xtext:
                parts.append("  " + xtext)
    return "\n".join(p for p in parts if p)


def main() -> int:
    oc = os.environ.get("LAW_OPEN_API_OC", "").strip()
    if not oc:
        print("환경변수 LAW_OPEN_API_OC 필요(법제처 OPEN API 기관코드)", file=sys.stderr)
        return 2
    q = urllib.parse.urlencode({"OC": oc, "target": "law", "MST": MST, "type": "JSON"})
    with urllib.request.urlopen(f"{SERVICE_URL}?{q}", timeout=40) as r:
        data = json.load(r)
    law = data["법령"]
    basic = law["기본정보"]
    arts = law["조문"]["조문단위"]

    docs = []
    for art in arts:
        num = str(art.get("조문번호"))
        branch = art.get("조문가지번호")  # 제35조의2 등 가지 조문 제외(기본 조문만)
        is_base = branch in (None, "", "0", "00")
        if num in WANT and is_base and art.get("조문여부") == "조문" and art.get("조문제목"):
            text = _flatten_article(art)
            docs.append({
                "doc_id": f"pipa-art{num}",
                "law": "개인정보 보호법",
                "article_no": f"제{num}조",
                "title": art.get("조문제목"),
                "text": text,
                # 무결성 근거: 원문 텍스트 해시(수동 편집·변조 탐지용)
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
    # 조문 번호 순 정렬(결정성)
    docs.sort(key=lambda d: int(d["doc_id"].replace("pipa-art", "")))

    # 코퍼스 무결성 해시 = (doc_id, article_no, title, text_sha256)을 doc_id로 정렬해 이어붙인 sha256
    # 스냅샷이 근거 라벨로 쓰는 메타(article_no·title)까지 묶어, 본문뿐 아니라 조문 식별자 변조도 잡는다.
    # (정렬 기준·필드 구성은 실습 본체 corpus_content_hash와 동일해야 한다)
    fingerprint = "|".join(f"{d['doc_id']}:{d['article_no']}:{d['title']}:{d['text_sha256']}"
                           for d in sorted(docs, key=lambda x: x["doc_id"]))
    content_hash = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    corpus = {
        "corpus_id": "pipa_core_articles",
        "law": "개인정보 보호법",
        "law_id": "011357",
        "mst": MST,
        "promulgation_no": str(basic.get("공포번호")),
        "promulgation_date": str(basic.get("공포일자")),
        "enforce_date": str(basic.get("시행일자")),
        "competent_authority": basic.get("소관부처", {}).get("content")
        if isinstance(basic.get("소관부처"), dict) else basic.get("소관부처"),
        "source": "국가법령정보센터 OPEN API(법제처)",
        "source_page": HUMAN_URL,
        "content_hash": content_hash,  # 실습 본체가 재계산해 무결성 검증
        "documents": docs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(corpus, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8")
    print(f"코퍼스 저장: {OUT} — 문서 {len(docs)}건")
    for d in docs:
        print(f"  {d['doc_id']}: {d['article_no']} {d['title']} ({len(d['text'])}자)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
