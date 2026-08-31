#!/usr/bin/env python3
"""12주차 통합 실습 실행기: 피처 거버넌스와 공정성·설명가능성.

실행 순서:
  1. run_governance.py: 카탈로그·접근 제어·품질·감사 점검
  2. run_fairness.py: 그룹별 성능·설명·모델 카드·정책 루브릭

실행: python run_chapter12.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def run(name: str) -> None:
    result = subprocess.run([sys.executable, str(BASE_DIR / name)], cwd=BASE_DIR)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    run("run_governance.py")
    run("run_fairness.py")
