#!/usr/bin/env python3
"""Chapter 8: Feast 최소 피처 저장소 — 실습 실행기.

실행:
    cd practice/chapter7
    source venv/bin/activate
    python run_chapter7.py
증거 산출물: data/output/ch7_feature_report.json
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run(
            [sys.executable, str(BASE_DIR / "code" / "7-1-feature-store-minimal.py")],
            cwd=BASE_DIR,
        ).returncode
    )
