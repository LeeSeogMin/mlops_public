#!/usr/bin/env python3
"""Chapter 5: 중복 이벤트 주입과 제거 검증 — 실습 실행기.

실행:
    python3 run_chapter5.py
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run(
            [sys.executable, str(BASE_DIR / "code" / "5-1-deduplicate-events.py")],
            cwd=BASE_DIR,
        ).returncode
    )
