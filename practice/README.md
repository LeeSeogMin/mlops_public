# 강의 실습

`practice/chapterN/`의 `N`은 상세 원고의 장 번호가 아니라 강의 주차 번호다. 중간고사 8주차와 기말고사 15주차에는 실습 폴더가 없다.

| 주차 | 강의 문서 | 실습 폴더 | 실습 내용 |
|---:|---|---|---|
| 1 | `lecture/ch01.md` | `chapter1/` | API 수집과 데이터 흐름 |
| 2 | `lecture/ch02.md` | `chapter2/` | 데이터 품질 탐색 |
| 3 | `lecture/ch03.md` | `chapter3/` | Kafka 최소 구성 |
| 4 | `lecture/ch04.md` | `chapter4/` | Kafka 전달 보장과 중복 제거 |
| 5 | `lecture/ch05.md` | `chapter5/` | 스트리밍 윈도와 지연 이벤트 |
| 6 | `lecture/ch06.md` | `chapter6/` | Airflow 일별 배치 파이프라인 |
| 7 | `lecture/ch07.md` | `chapter7/` | 피처 저장소와 시점 일관성 |
| 9 | `lecture/ch09.md` | `chapter9/` | 실험 추적과 모델 등록 |
| 10 | `lecture/ch10.md` | `chapter10/` | 모델 서빙 |
| 11 | `lecture/ch11.md` | `chapter11/` | 모니터링 |
| 12 | `lecture/ch12.md` | `chapter12/` | 피처 거버넌스와 공정성·설명가능성 |
| 13 | `lecture/ch13.md` | `chapter13/` | 통합 MLOps 파이프라인 |
| 14 | `lecture/ch14.md` | `chapter14/` | LLMOps |

각 폴더의 기본 실행 파일은 `run_chapterN.py`다. 4주차와 12주차의 통합 실행 파일은 두 세부 실습을 순서대로 호출한다.

환경만 점검하려면 저장소 루트에서 다음 명령을 사용한다.

```bash
python scripts/setup_practice.py N --check
```
