# D009 — 데이터 품질 진단 및 EDA 보고서

## 사용 데이터
**선택 2. 외부 데이터** — KBO 팬 멤버십/구매 실습용 샘플 데이터 (`data/kbo_fan_data_sample.csv`)

Kaggle이나 공공데이터포털 데이터가 아니라 커리큘럼 실습을 위해 제공된 합성(synthetic) 데이터입니다.
자세한 출처와 선정 이유는 [`data/source_note.md`](./data/source_note.md)를 참고해 주세요.

> ⚠️ 원본 데이터에는 `email` 컬럼이 있었지만, 개인정보 보호를 위해 분석 시작 전 **컬럼 자체를 제거**한
> 뒤 진행했습니다. 이 폴더에 올라간 CSV도 email이 제거된 버전입니다.

## 노트북
[`D009_data_quality_eda_report.ipynb`](./D009_data_quality_eda_report.ipynb)

위에서부터 아래로 오류 없이 실행되며, 아래 순서로 구성되어 있습니다.

1. 데이터 개요 (출처·관측 단위·주요 컬럼 설명)
2. 데이터 품질 진단 (`quality_report_full()` 결과 + 표기 혼재 직접 확인)
3. 정제 과정과 판단 근거 (중복 → 문자열 → 날짜 → 이상치 → 결측치, `.pipe()`로 연결, 결정 로그 5건)
4. EDA 결과 (단일 변수 분포, 구단별 비교, 가입연도별 추이, 멤버십 등급별 KPI + 인사이트 2건)
5. 결과 저장 (Parquet vs CSV 용량 비교)
6. 한계와 후속 질문

## 정제 요약

| 항목 | 정제 전 | 정제 후 |
|---|---|---|
| 행 수 | 5,075 | 4,887 |
| region 표기 종류 | 70종 | 10종 |
| favorite_team 표기 종류 | 50종 | 10종 |
| season_ticket_yn 표기 종류 | 8종 | 2종 (0/1) |
| join_date / last_purchase_date 자료형 | object | datetime64[ns] |

## 핵심 인사이트
1. 팬 수가 가장 많은 구단(LG Twins)과 팬 1인당 평균 지출이 가장 높은 구단(NC Dinos)이 서로 다르다.
2. 멤버십 등급(Bronze~VIP)과 평균 지출액이 뚜렷한 정비례 관계를 보이지 않는다 — 등급 산정 기준에 대한
   후속 확인이 필요하다.

## 폴더 구조
```
D009/
├── D009_data_quality_eda_report.ipynb
├── README.md
├── data/
│   ├── kbo_fan_data_sample.csv   # email 컬럼 제거된 버전
│   └── source_note.md
└── outputs/
    ├── cleaned_data.parquet
    ├── kpi_team_summary.parquet
    ├── kpi_membership_summary.parquet
    ├── kpi_year_trend_summary.parquet
    ├── eda_total_spent_hist.png
    ├── eda_team_avg_spent_bar.png
    └── eda_year_trend.png
```
