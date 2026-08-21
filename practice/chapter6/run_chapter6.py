#!/usr/bin/env python3
"""Chapter 6: 지역별 민원 이벤트 윈도우 집계 — 실습 실행기.

선수 조건: Java 17+ (JAVA_HOME 설정), pip install -r code/requirements.txt

실행:
    python3 run_chapter6.py
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run(
            [sys.executable, str(BASE_DIR / "code" / "6-1-streaming-window-aggregation.py")],
            cwd=BASE_DIR,
        ).returncode
    )
