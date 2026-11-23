#!/usr/bin/env python3
"""학기 운영 게이트 (basic_DL 저장소의 course_gates.py를 이 저장소에 맞게 옮긴 것).

학기 중의 위험은 "장을 안 썼다"가 아니라 "고친 뒤 뒤따라야 할 것을 안 고쳤다"이다.
세 가지를 검사한다.

  G1 실행 증거 무결성 — 코드를 고치고 결과를 다시 만들지 않은 장이 있는가
  G2 본문 인용 경로 실존 — lecture 원고가 가리키는 practice/ 파일이 실제로 있는가
  G3 md - PDF 동기     — 원고를 고치고 PDF를 다시 만들지 않은 장이 있는가

검사 로직은 새로 쓰지 않고 run_and_capture.py의 것을 그대로 쓴다.

사용법:
  python3 scripts/course_gates.py
  python3 scripts/course_gates.py --gates g1,g2
  python3 scripts/course_gates.py --verbose
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from run_and_capture import (  # noqa: E402
    PRACTICE_DIR,
    discover_code_files,
    sha256_of_text,
    verify as verify_chapter,
)

LECTURE_DIR = PROJECT_ROOT / "lecture"

# 원고가 인용한 practice/ 경로. 예: # 출처: practice/chapter11/results/run_chapter11.log
# 경로 안의 {N}·* 같은 자리표시는 검사하지 않는다.
CITATION_RE = re.compile(
    r"(?<![\w/{])(practice/chapter\d+/[^\s`'\"()（）,]*[^\s`'\"()（）,.。:;])"
)

# G1에서 빼는 파일과 이유. 증거 게이트가 돌리는 방식(인자 없이, 외부 서비스 없이)으로는
# 실행할 수 없는 파일만 적는다. 낡은 결과를 숨기려고 여기에 넣지 않는다.
G1_EXEMPT = {
    "chapter1/1-1-public-api.py": "data.go.kr 인증키가 필요한 실제 API 호출",
    "chapter4/4-1-kafka-producer.py": "Kafka 브로커가 떠 있어야 실행됨",
    "chapter4/4-2-kafka-consumer.py": "Kafka 브로커가 떠 있어야 실행됨",
    "chapter11/11-0-collect-snapshot.py": "data.go.kr 인증키 필요, 입력 스냅샷을 덮어씀",
    "chapter12/12-1-feature-governance.py": "--input/--output 인자 필요, run_governance.py가 부름",
    "chapter12/12-2-fairness-xai.py": "--input/--output 인자 필요, 오케스트레이터가 부름",
    "chapter12/verify_fairness_numbers.py": "옛 상세 원고 수치 대조 도구(실습 코드 아님)",
    "chapter12/verify_governance_numbers.py": "옛 상세 원고 수치 대조 도구(실습 코드 아님)",
    "chapter13/00-build-corpus.py": "법제처 OPEN API 기관코드(LAW_OPEN_API_OC) 필요",
    "chapter13/13-1-prompt-registry.py": "--input/--output 인자 필요, 오케스트레이터가 부름",
    "chapter13/13-2-llm-snapshot.py": "LLM API 키 필요, 비결정 출력(재현 게이트 밖)",
}


def chapter_number(name: str) -> int:
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 0


def gate_evidence(verbose: bool) -> tuple[int, int]:
    """G1. 모든 장의 실습 코드와 증거 JSON의 소스 해시가 맞는지 본다."""
    chapter_dirs = sorted(
        (d for d in PRACTICE_DIR.glob("chapter*") if (d / "code").is_dir()),
        key=lambda d: chapter_number(d.name),
    )

    checked = 0
    problems = 0
    exempted = 0
    for chapter_dir in chapter_dirs:
        files = []
        for f in discover_code_files(chapter_dir, None, include_manual=True):
            key = f"{chapter_dir.name}/{f.name}"
            if key in G1_EXEMPT:
                exempted += 1
                if verbose:
                    print(f"[exempt] {key} — {G1_EXEMPT[key]}")
                continue
            files.append(f)
        if not files:
            continue
        checked += len(files)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            found = verify_chapter(chapter_dir, files)
        problems += found
        for line in buf.getvalue().splitlines():
            if verbose or "✅" not in line:
                print(f"[{chapter_dir.name}]{line}")

    print(f"[G1] 실행 증거 무결성: {checked}개 파일 검사, 문제 {problems}건, "
          f"면제 {exempted}개(--verbose로 사유 확인)")
    return checked, problems


def gate_citations(verbose: bool) -> tuple[int, int]:
    """G2. 원고가 인용한 practice/ 경로가 실제로 있는지 본다."""
    checked = 0
    problems = 0

    md_files = sorted(LECTURE_DIR.glob("ch*.md"), key=lambda p: chapter_number(p.stem))
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        for match in CITATION_RE.finditer(text):
            rel = match.group(1)
            checked += 1
            if not (PROJECT_ROOT / rel).exists():
                print(f"[missing] 인용한 경로가 없음: {md_path.name} -> {rel}")
                problems += 1
            elif verbose:
                print(f"[ok] 인용 확인: {md_path.name} -> {rel}")

    print(f"[G2] 본문 인용 경로 실존: {checked}건 검사, 문제 {problems}건")
    return checked, problems


def gate_pdf_sync(verbose: bool) -> tuple[int, int]:
    """G3. PDF를 만든 시점의 원고 해시와 지금 원고 해시를 맞춰 본다.

    md2pdf.py가 변환할 때 남긴 lecture/ch{N}.pdf.evidence.json의 해시를 쓴다.
    """
    checked = 0
    problems = 0
    unrecorded: list[str] = []

    pdf_files = sorted(LECTURE_DIR.glob("ch*.pdf"), key=lambda p: chapter_number(p.stem))
    for pdf_path in pdf_files:
        md_path = pdf_path.with_suffix(".md")
        if not md_path.exists():
            print(f"[orphan] 원본 마크다운이 없는 PDF: {pdf_path.name}")
            problems += 1
            continue

        evidence_path = pdf_path.with_name(pdf_path.name + ".evidence.json")
        if not evidence_path.exists():
            unrecorded.append(pdf_path.name)
            continue

        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        checked += 1
        current = sha256_of_text(md_path.read_text(encoding="utf-8"))
        if current != evidence.get("source_sha256"):
            print(
                f"[stale] 원고를 고친 뒤 PDF를 다시 만들지 않음: {pdf_path.name} "
                f"- python3 scripts/md2pdf.py {md_path.relative_to(PROJECT_ROOT).as_posix()}"
            )
            problems += 1
        elif verbose:
            print(f"[ok] PDF 동기: {pdf_path.name}")

    note = ""
    if unrecorded:
        note = f", 생성 기록 없어 건너뜀 {len(unrecorded)}개({', '.join(unrecorded)})"
    print(f"[G3] md-PDF 동기: PDF {len(pdf_files)}개 중 {checked}개 검사, 문제 {problems}건{note}")
    return checked, problems


GATES = {
    "g1": gate_evidence,
    "g2": gate_citations,
    "g3": gate_pdf_sync,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="MLOps 강의 학기 운영 게이트")
    parser.add_argument("--gates", default="g1,g2,g3", help="실행할 게이트. 기본값 g1,g2,g3")
    parser.add_argument("--verbose", action="store_true", help="통과한 항목도 한 줄씩 출력한다")
    args = parser.parse_args()

    selected = [name.strip().lower() for name in args.gates.split(",") if name.strip()]
    unknown = [name for name in selected if name not in GATES]
    if unknown:
        print(f"모르는 게이트: {', '.join(unknown)} (가능: g1, g2, g3)")
        return 1

    total_checked = 0
    total_problems = 0
    for name in selected:
        checked, problems = GATES[name](args.verbose)
        total_checked += checked
        total_problems += problems

    print(f"게이트 합계: {total_checked}건 검사, 문제 {total_problems}건")

    if total_checked == 0:
        print("COURSE_GATES_FAIL: 검사 대상을 하나도 찾지 못했다. 경로 설정을 확인한다.")
        return 1

    if total_problems:
        print(f"COURSE_GATES_FAIL: 문제 {total_problems}건")
        return 1

    print("COURSE_GATES_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
