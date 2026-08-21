# 운영 개선 체크리스트 (자동 생성 — 실습 17.1)

총 10항목 — 사건·error budget에서 도출.

- [ ] [8장] 적재 후 건수 확인 게이트 + 온라인·오프라인 일관성 대조(표 8.2)  
  근거: INC-08-materialize-silent-empty
- [ ] [9장] 등록 직후 로드·예측 스모크(시나리오 4 통과가 PASS 조건)  
  근거: INC-09-runs-uri-load-fail
- [ ] [10장] 컨테이너 스모크 독립 게이트 + 환경 동등성(호스트=컨테이너 예측) 실측  
  근거: INC-10-container-path-indexerror
- [ ] [12장] 배포 전 부하 프로파일로 처리량 천장·knee 지점 측정, 자동 스케일 임계 설정  
  근거: INC-12-single-worker-saturation
- [ ] [14장] 파싱 실패 격리 + 격리 건수 모니터링  
  근거: INC-14-D1-poison-isolation
- [ ] [14장] at-least-once ↔ 멱등 UPSERT 한 쌍 유지, 파티션 수 검증  
  근거: INC-14-D2-duplicate-resend
- [ ] [14장] 부분 실패 격리 + 재시도 큐 + 마감/예측 의존 분리  
  근거: INC-14-D3-api-outage-recovery
- [ ] [15장] 생성 엔드포인트 헬스체크 + 멀티벤더 폴백  
  근거: INC-15-openai-billing-429
- [ ] error budget 소진 시 신규 배포 동결(SRE error budget policy)  
  근거: ch17_error_budget.json
- [ ] 포스트모템은 비난 없이(blameless) — 사람이 아니라 시스템·절차를 고친다  
  근거: SRE Postmortem Culture
