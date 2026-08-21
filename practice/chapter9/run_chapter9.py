#!/usr/bin/env python3
"""Chapter 9: MLflow 실험 기록·모델 레지스트리 — 실습 실행기.

실행:
    cd practice/chapter9
    source venv/bin/activate
    python run_chapter9.py
증거 산출물: data/output/ch9_experiment_report.json
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(
        subprocess.run(
            [sys.executable, str(BASE_DIR / "code" / "9-1-mlflow-tracking.py")],
            cwd=BASE_DIR,
        ).returncode
    )
