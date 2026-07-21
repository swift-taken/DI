# KBO 팬 데이터 정제·집계 보고서

## 1. 데이터 개요

* 출처: (실습용 합성 데이터) KBO 팬 멤버십/구매 로그 — 자세한 내용은 `data/source_note.md` 참고
* 기간: join_date 2015-01-01 ~ 2024-12-30 (가입일 기준)
* 원본 행 수 / 정제 후 행 수: (5,075)행 → (4,887)행

## 2. 발견한 품질 문제

* 결측: membership_tier 5.02% / sns_follow_yn 10.27% / region 4.02%
* 중복: 완전 중복 50건 + 동일 customer_id인데 값이 다른 25건 (총 75건)
* 이상치: total_spent 2.33% / attended_games 0.45% (IQR 기준)
* 표기 혼재: region 70종(`Seoul` / `SEOUL` / `Seoul City` / `seoul-si`) → favorite_team 50종(`doosan bears` / `DoosanBears`)

## 3. 처리 결정과 근거 (5줄로)

1. 중복 행 50건 → 완전 동일한 행은 시스템 입력 오류로 간주, 제거. 이후 남은 동일 customer_id 25건은 같은 고객의 다른 시점 스냅샷으로 보고, 가장 최근 값만 남깁니다.
2. region/favorite_team 공백·대소문자·접미사 표기 → 표준 명칭으로 통일 (region 70종→10종, favorite_team 50종→10종)
3. join_date/last_purchase_date 날짜 포맷 4종 혼재 → 표기 패턴별로 구분해 datetime으로 변환
4. age(0~100 밖) 8건, purchase_count(음수) 15건 → 결측 처리. total_spent 상단 이상치는 VIP 고액 소비 가능성으로 유지(제거하지 않음)
5. purchase_count 결측 113건 → 제거 (이유: 구매 KPI 핵심 지표라 결측 시 집계 왜곡). 그 외 인구통계/부가정보 컬럼은 'Unknown' 처리 후 유지

## 4. 주요 KPI 결과 (2줄)

* (지역·월 관점) 매출이 가장 컸던 조합: 2018-02 "Seoul" (총 7,909,463원)
* (구단 관점) 평균 지출 1위 구단: NC Dinos (팬 393명, 평균 287,656원)

## 5. 한계와 후속 작업

* membership_tier와 평균 지출액이 정비례하지 않는 원인 분석 필요 (등급 산정 기준 확인)
* sns_follow_yn·membership_tier 결측 원인 분석 필요
* 구단 성적, 시즌별 프로모션 등 외부 데이터 추가 수집 필요
