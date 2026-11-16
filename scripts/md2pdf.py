#!/usr/bin/env python3
"""강의 원고 마크다운을 PDF로 바꾸고, 생성 기록을 남긴다.

변환은 scripts/md2pdf_engine.py(pandoc + Chrome headless)가 한다.
이 래퍼는 변환이 끝난 뒤 lecture/ch{N}.pdf.evidence.json에 원본 마크다운의
해시를 남긴다. course_gates.py의 G3가 이 해시와 지금 원본의 해시를 비교해
"본문을 고치고 PDF를 다시 만들지 않은" 장을 찾는다.

git은 파일 수정 시각을 보존하지 않으므로, 시각이 아니라 해시로 비교한다.

사용법:
  python3 scripts/md2pdf.py lecture/ch11.md
  python3 scripts/md2pdf.py lecture/ch11.md lecture/ch12.md
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
ENGINE = SCRIPTS_DIR / "md2pdf_engine.py"
sys.path.insert(0, str(SCRIPTS_DIR))

# 해시 함수를 실행 증거 게이트와 같은 것으로 쓴다.
from run_and_capture import sha256_of_text  # noqa: E402


def relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def pandoc_version() -> str:
    found = shutil.which("pandoc")
    if not found:
        return ""
    result = subprocess.run([found, "--version"], capture_output=True, text=True)
    return result.stdout.splitlines()[0].strip() if result.stdout else ""


def write_pdf_evidence(md_path: Path, pdf_path: Path) -> Path:
    evidence = {
        "source_markdown": relpath(md_path),
        "source_sha256": sha256_of_text(md_path.read_text(encoding="utf-8")),
        "output_pdf": relpath(pdf_path),
        "output_bytes": pdf_path.stat().st_size,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "pandoc": pandoc_version(),
        "engine": relpath(ENGINE),
    }
    evidence_path = pdf_path.with_name(pdf_path.name + ".evidence.json")
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence_path


def main() -> int:
    parser = argparse.ArgumentParser(description="강의 원고 PDF 변환 + 생성 기록")
    parser.add_argument("markdown", nargs="+", help="변환할 마크다운 파일")
    args = parser.parse_args()

    for item in args.markdown:
        md_path = Path(item).resolve()
        if not md_path.exists():
            print(f"파일을 찾을 수 없습니다: {item}")
            return 1
        pdf_path = md_path.with_suffix(".pdf")
        # 지금까지 PDF를 만들던 방식(저장소 루트에서 실행)과 같게 한다.
        cmd = [sys.executable, str(ENGINE), str(md_path), "--out", str(pdf_path)]
        if subprocess.run(cmd, cwd=PROJECT_ROOT).returncode != 0:
            print(f"PDF 변환 실패: {relpath(md_path)} — 생성 기록을 남기지 않는다")
            return 1
        evidence_path = write_pdf_evidence(md_path, pdf_path)
        print(f"생성 기록: {relpath(evidence_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
