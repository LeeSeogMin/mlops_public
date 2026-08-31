#!/usr/bin/env python3
"""4주차 통합 실습 실행기: Kafka 전달 보장과 중복 제거.

실행 순서:
  1. run_kafka.py: 전달 방식별 유실·중복 관찰
  2. run_dedup.py: at-least-once 처리 기록의 중복 제거

실행: python run_kafka.py
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
    run("run_kafka.py")
    run("run_dedup.py")
