# MLOps 강의자료

공공 AI 서비스의 데이터 수집, 품질 관리, 모델 운영, 모니터링과 검수 과정을 실습하는 강의자료다.

## 학생용 자료

- `lecture/`: 학부 3–4학년용 강의 원고(`ch01.md`–`ch17.md`)
- `practice/`: 장별 실행 코드, 입력자료와 실제 실행 산출물
- `syllabus.md`: 과목 운영과 장별 학습 흐름
- `INSTALLATION.md`: 실습 환경 설치 안내

각 장의 실습은 해당 `practice/chapterN/`에서 시작한다. 장별 `run_chapterN.py`는 전체 실습 흐름을 확인하는 진입점이며, 세부 코드는 `code/` 아래에 둔다.

## 기본 실행 흐름

```bash
cd practice/chapter{N}
python3 -m venv venv
# macOS/Linux: source venv/bin/activate
# Windows: venv\Scripts\activate
pip install -r requirements.txt
python run_chapter{N}.py
```

운영체제나 Python 버전에 따라 일부 장은 별도 의존성이나 Docker가 필요하다. 자세한 조건은 장별 README와 `requirements.txt`를 먼저 확인한다.

## 자료의 성격

강의 원고는 실무교재를 학부 수업용으로 다시 설명한 파생 자료다. 실습 산출물의 수치와 사례는 저장소에 포함된 실행 결과를 기준으로 하며, 개인용 연구 초안·내부 메모·원고 설계 파일은 이 공개 저장소에 포함하지 않는다.


