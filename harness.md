# MLOps 강의자료 하네스

> basic_DL 저장소의 학기 운영 하네스(`harness.md`, `scripts/course_gates.py`, `harness.sh`, `verify.sh`, PDF 생성 기록)를 이 저장소에 맞게 옮긴 것이다. 옮긴 날: 2026-11-16.

## 1. 이 하네스가 막는 것

하네스는 "하겠다"는 규칙을 "했다"는 증거로 바꾸는 장치다. 산문으로 적은 지시는 지켰는지 확인할 수 없지만, 파일과 종료 코드는 확인할 수 있다.

이 저장소는 학기 중 운영기다. 주된 위험은 **고친 뒤 뒤따라야 할 것을 안 고치는 것**이며, 세 가지 모양으로 나타난다.

1. 실습 코드를 고치고 결과 로그를 다시 만들지 않는다. 원고 수치가 옛 코드의 것으로 남는다.
2. 원고(`lecture/ch{N}.md`)를 고치고 PDF를 다시 만들지 않는다. 학생이 받는 PDF와 저장소의 원고가 달라진다.
3. 원고가 가리키는 `practice/` 파일이 옮겨지거나 지워져, 출처를 되짚을 수 없게 된다.

## 2. 절대 규칙

- 실행하지 않은 코드 결과를 원고에 쓰지 않는다. 원고의 수치는 `practice/chapter{N}/results/*.log`와 `data/output/` 산출물에서만 가져온다.
- 인용한 출력 블록 첫 줄에 `# 출처: practice/chapter{N}/results/파일명.log`를 붙인다. G2가 이 경로가 실제로 있는지 확인한다.
- 설명을 위해 만든 사례·숫자는 원고에서 만든 것이라고 밝힌다(예: 11장 가람구 사례).
- 로그에는 코드가 출력한 것만 남는다. 원고에 인용할 값은 먼저 코드가 출력하게 만든다.
- 요청 범위 밖의 문제는 고치지 말고 보고한다.

## 3. 학기 중 개정 루프

| 단계 | 하는 일 | 확인 명령 |
|---|---|---|
| 1 | 무엇을 왜 고치는지 정하고 고칠 파일을 연다 | — |
| 2 | 실습 코드를 고쳤으면 다시 실행해 증거를 새로 만든다 | `python3 scripts/run_and_capture.py {N} --file 파일명` |
| 3 | 원고 수치를 새 로그에 맞춘다 | `python3 scripts/run_and_capture.py {N} --verify` |
| 4 | 원고를 고쳤으면 PDF를 다시 만든다 | `python3 scripts/md2pdf.py lecture/ch{N}.md` |
| 5 | 게이트를 통과시킨 뒤 커밋한다 | `./scripts/harness.sh` |

설명 문장만 고쳤다면 2·3단계는 건너뛴다. 4단계는 건너뛰지 않는다. 원고를 한 줄만 고쳐도 PDF는 낡는다.

## 4. 게이트 (`scripts/course_gates.py`)

| 게이트 | 무엇을 비교하는가 | 실패할 때의 뜻 |
|---|---|---|
| G1 실행 증거 무결성 | 실습 코드의 sha256 해시 ↔ `results/*.evidence.json`의 `source_sha256` | 코드를 고치고 다시 실행하지 않았다 |
| G2 본문 인용 경로 실존 | `lecture/ch*.md`에 적힌 `practice/chapter{N}/...` 경로 ↔ 실제 파일 | 원고가 없는 파일을 근거로 대고 있다 |
| G3 md-PDF 동기 | 원고의 현재 해시 ↔ `lecture/ch{N}.pdf.evidence.json`의 생성 당시 해시 | 원고를 고치고 PDF를 다시 만들지 않았다 |

- **G1 면제**: 증거 게이트 방식(인자 없이, 외부 서비스 없이)으로는 실행할 수 없는 파일 11개를 `course_gates.py`의 `G1_EXEMPT`에 사유와 함께 적었다. 인증키가 필요한 API 호출, Kafka 브로커가 필요한 코드, `--input/--output` 인자를 받아 오케스트레이터가 부르는 코드, LLM 호출이 해당한다. 낡은 결과를 숨기려고 면제 목록에 넣지 않는다. `--verbose`로 사유를 본다.
- **G3 전제**: git은 파일 수정 시각을 보존하지 않으므로 해시로 비교한다. `scripts/md2pdf.py`로 만든 PDF만 생성 기록이 있고, 기록이 없는 PDF는 "생성 기록 없음"으로 건너뛴다. 그 장의 PDF를 이 스크립트로 다시 만들면 기록이 생긴다.
- **검사하지 않는 것**: 출력 블록의 줄이 로그와 글자 그대로 같은지는 게이트에 넣지 않았다. 2026-11-16 기준 817줄 중 27줄이 다르며(ch01·ch02·ch06·ch09), 일부는 로그를 요약하거나 경로를 바꿔 옮긴 것이라고 블록 안에 밝혀 둔 의도된 차이다.

## 5. 실행 방법

```bash
# 전체 게이트 (커밋 전)
./scripts/harness.sh

# 빠른 검증 (G1·G2만)
./scripts/verify.sh

# 게이트만, 통과 항목과 면제 사유까지
python3 scripts/course_gates.py --verbose
python3 scripts/course_gates.py --gates g1,g2

# 장별 실행 증거
python3 scripts/run_and_capture.py 11 --file 11-1-drift-monitoring.py
python3 scripts/run_and_capture.py 11 --verify

# 원고를 PDF로 (생성 기록 lecture/ch{N}.pdf.evidence.json을 함께 남김)
python3 scripts/md2pdf.py lecture/ch11.md
```

- `./scripts/harness.sh`는 성공하면 마지막 줄에 `HARNESS_PASS`, `./scripts/verify.sh`는 `VERIFY_PASS`를 출력한다.
- **두 스크립트는 검사를 하나 이상 실제로 했을 때만 통과를 출력한다.** ruff·pytest가 없는 기계에서도 게이트 검사가 돌아야 통과한다.
- PDF 변환 엔진 `scripts/md2pdf_engine.py`와 스타일 `scripts/md2pdf.css`는 korean-md-pdf 스킬에서 옮긴 것이다. 스킬이 없는 기계에서도 같은 결과가 나온다. 필요한 것은 pandoc과 Chrome(또는 Edge)이다.

## 6. 실패 시 행동 규칙

1. 누락된 산출물을 명시하고 다음 단계로 진행하지 않는다.
2. 실행 로그가 없으면 원고 수치를 쓰지 않는다.
3. 낡은 결과(`낡은 결과`, `[stale]`)가 나오면 코드를 다시 실행하거나 PDF를 다시 만든다. 증거 JSON을 손으로 고치지 않는다.
4. 코드가 실패하면 실패 로그를 남기고 원인을 고친다.
5. 게이트를 못 돌린 채 완료를 보고하지 않는다. 못 돌렸으면 무엇을 왜 못 돌렸는지 적는다.
6. 반복 함정은 `.claude/lessons-learned.md`에 적고, 같은 함정이 3회 반복되면 `.claude/GOTCHAS.md`로 올린다.
