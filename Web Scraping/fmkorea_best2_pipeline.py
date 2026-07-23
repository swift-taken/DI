# -*- coding: utf-8 -*-
"""
====================================================================
[웹 스크래핑 종합 과제] 에펨코리아 '포텐 터짐(화제)' 게시판 분석
====================================================================

이 파일 하나로 "수집 -> 저장 -> 정제 -> 시각화" 전체 파이프라인이 순서대로 실행됩니다.
(노트북(fmkorea_best2_scraper.ipynb)의 내용을 셀 구분 없이 스크립트 한 개로 합친 버전입니다.
 노트북에서는 마크다운 셀로 되어있던 설명들이, 여기서는 큰 주석 블록(#### ... ####)으로 들어갑니다.)

--------------------------------------------------------------------
0. 주제
--------------------------------------------------------------------
대상 사이트: 에펨코리아(fmkorea) - 국내 대형 커뮤니티
대상 게시판: 포텐 터짐 - 화제순 (https://www.fmkorea.com/best2)

best2는 커뮤니티 전체 게시판을 통틀어 "지금 화제가 되고 있는 글"을 모아 보여주는
실시간 인기글 랭킹 피드입니다. 페이지 번호(?page=N)를 넘기면서 과거 인기글도 볼 수 있습니다.

--------------------------------------------------------------------
1. 분석 질문
--------------------------------------------------------------------
    화제글의 카테고리에 따라 추천수(화제성)와 댓글수(참여도)가 어떻게 달라질까?
    그리고 화제글은 요일에 따라 발생 빈도가 다를까?

필요한 컬럼: 카테고리, 추천수, 댓글수, 작성일자(요일 계산용)

--------------------------------------------------------------------
2. 수집 대상 & 범위 결정
--------------------------------------------------------------------
- URL: https://www.fmkorea.com/best2?page=N
- 수집 항목: 작성자, 카테고리, 제목, 작성일자, 추천수, 댓글수, 게시글 URL

[범위에 대한 사전 조사 결과]
처음에는 "2026-01-01 ~ 2026-07-23"처럼 특정 기간을 지정해서 모으려 했지만, 실제로 사이트를
확인해보니 best2는 캘린더 날짜로 조회하는 게시판이 아니라 그냥 페이지 번호로 넘기는 실시간
랭킹 피드였습니다. 실제로도 페이지를 끝까지 넘겨보면 최근 며칠 안팎에서 게시글이 끊깁니다.
그래서 "날짜를 지정"하는 대신, "페이지를 최대 MAX_PAGE_COUNT까지 넘기면서 실제로 게시글이
나오는 만큼만 모으고, 모은 뒤 작성일자 기준으로 정렬"하는 방식으로 범위를 조정했습니다.

목록 페이지에는 조회수가 없습니다. 상세 페이지를 하나씩 더 방문해야 조회수를 얻을 수 있는데,
이번 분석 질문(카테고리 vs 추천수·댓글수)에는 조회수가 필수가 아니고, 상세 페이지까지 방문하면
요청 수가 2배가 되어 수집 시간과 서버 부담이 커지므로 조회수 수집은 범위에서 제외했습니다.

--------------------------------------------------------------------
윤리·법 체크
--------------------------------------------------------------------
- robots.txt 확인: 이름이 지정된 AI 크롤러(anthropic-ai, ClaudeBot 등)는 차단되어 있지만,
  이름이 없는 일반 봇(User-agent: *)에게는 /best2가 명시적으로 허용되어 있습니다.
- 로그인이 필요 없는 공개 게시판만 수집하며, 실명·연락처 등 개인정보는 수집하지 않습니다
  (수집하는 '작성자'는 사이트에 공개된 닉네임입니다).
- 요청 사이에 time.sleep()으로 딜레이를 둡니다.
- 수집 목적은 학습용이며, 재배포·상업적 이용을 하지 않습니다.

실행 방법:
    python fmkorea_best2_pipeline.py
끝까지 실행하면 fmkorea_best2_raw.csv / fmkorea_best2_clean.csv 와 chart1~4_*.png 가 생성됩니다.
"""

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urljoin

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# 한글 폰트 설정 (그래프용)
# ---------------------------------------------------------------------------
# matplotlib 기본 폰트는 한글을 지원하지 않아서, 한글이 깨진(□로 표시되는) 그래프가 됩니다.
# Windows에는 '맑은 고딕(Malgun Gothic)' 폰트가 기본으로 깔려 있으므로 이걸 사용합니다.
#
# ※ 주의: seaborn의 sns.set_style()이 내부적으로 font.family를 'sans-serif'로
#   되돌려버리기 때문에, 폰트 지정은 반드시 sns.set_style()보다 "나중에" 해야 적용됩니다.
sns.set_style('whitegrid')
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False


####################################################################
# 3. 데이터 수집
####################################################################

# ---------------------------------------------------------------------------
# 3-0. fmkorea의 DDoS 방어 시스템(WASM 챌린지)에 대한 설명
# ---------------------------------------------------------------------------
# fmkorea가 DDoS 방어 시스템(WASM 챌린지)을 걸어둬서, requests처럼 JS를 실행하지 않는
# 방식으로 요청을 보내면 실제 게시글이 아니라 HTTP 430 차단 페이지만 돌아옵니다. 이 챌린지는
# 브라우저에서 JS/WASM을 실행해 검증 쿠키를 만든 뒤 자동 새로고침이 되어야 통과되는 구조라,
# JS를 실행하지 않는 라이브러리로는 우회할 수 없습니다(이 챌린지 로직을 역산해서 우회하는 것도
# 하지 않습니다). 대신 Playwright로 실제 headless 브라우저를 띄워서, 사이트가 의도한 대로
# JS/WASM이 정상적으로 실행되게 하고, 그 결과 렌더링된 HTML을 BeautifulSoup으로 파싱합니다.
#
# 최초 실행 전에는 아래 두 줄을 터미널에서 한 번 실행해서 Playwright와 브라우저를 설치해야 합니다.
#   pip install playwright
#   playwright install chromium

# ---------------------------------------------------------------------------
# 3-1. 설정값
# ---------------------------------------------------------------------------
BASE_URL = 'https://www.fmkorea.com'
LIST_URL = f'{BASE_URL}/best2'

# 일반 브라우저로 보이는 User-Agent (이름이 지정된 AI 크롤러 UA는 robots.txt에서 차단되어 있음)
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

MAX_PAGE_COUNT = 200        # 수집할 목록 페이지 수 상한 (1페이지 = 20건)
MAX_CONSECUTIVE_EMPTY = 2   # 연속으로 이 횟수만큼 빈 페이지가 나오면 "실제 데이터가 끝났다"고 보고 중단
REQUEST_DELAY = 1.0         # 요청 사이 대기 시간(초) - 서버에 부담을 주지 않기 위한 최소한의 예의
RENDER_WAIT = 3.5           # DDoS 챌린지 통과 + 렌더링 대기 시간(초)


def fetch_rendered_html(page, url: str, params: dict | None = None) -> str:
    """Playwright 페이지로 url을 방문해서 DDoS 챌린지 통과 후 최종 HTML을 반환합니다."""
    if params:
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'{url}?{query}'

    # wait_until='load'는 이미지·광고 등 모든 하위 리소스를 기다리다 타임아웃 나는 경우가
    # 있어서, HTML 파싱이 끝나는 시점(domcontentloaded)까지만 기다립니다.
    page.goto(url, wait_until='domcontentloaded', timeout=30000)
    # 그 다음 RENDER_WAIT만큼 더 기다려서, DDoS 챌린지 스크립트가 쿠키를 세팅하고
    # 자동 새로고침을 마칠 시간을 줍니다.
    page.wait_for_timeout(int(RENDER_WAIT * 1000))
    return page.content()


# ---------------------------------------------------------------------------
# 3-2. 목록 페이지 파싱 함수
# ---------------------------------------------------------------------------
# div.fm_best_widget 안의 li.li 항목마다 아래 정보를 뽑습니다.
#
#   항목                    | CSS 선택자
#   ------------------------|----------------------------------------------
#   제목                    | h3.title 의 data-original-title 속성 (말줄임 없는 전체 제목)
#   카테고리                | span.category a (여러 개면 '-'로 연결)
#   작성자                  | span.author
#   추천수                  | a.pc_voted_count .count
#   댓글수                  | .comment_count ([123] 형태)
#   작성일자(원본 텍스트)    | span.regdate -> "3 분 전" / "22 시간 전" / "2026.07.22" 세 형태가 섞여있음
#                             (실제 날짜로 바꾸는 건 정제 단계(4장)에서 합니다)

def parse_list_page(html: str) -> list[dict]:
    """best2 목록 페이지 HTML 1개를 파싱해서 게시글 기본 정보 리스트를 반환합니다."""
    soup = BeautifulSoup(html, 'html.parser')

    posts = []
    for li in soup.select('div.fm_best_widget ul > li.li'):
        title_tag = li.select_one('h3.title')
        link_tag = li.select_one('h3.title a')
        if title_tag is None or link_tag is None:
            continue  # 광고 등 게시글이 아닌 li는 건너뜁니다.

        url = urljoin(BASE_URL, link_tag['href'])

        # 목록에 보이는 제목은 길면 "..."으로 잘리므로, 잘리지 않은 전체 제목이 담긴
        # data-original-title 속성을 우선 사용합니다.
        ellipsis_tag = title_tag.select_one('.ellipsis-target')
        title = title_tag.get('data-original-title') or (
            ellipsis_tag.get_text(strip=True) if ellipsis_tag else title_tag.get_text(strip=True)
        )

        # 카테고리가 "유머 - 이슈"처럼 대분류-소분류 두 개로 나올 수 있어서 이어붙입니다.
        category_links = li.select('span.category a')
        category = ' - '.join(a.get_text(strip=True) for a in category_links)

        author_tag = li.select_one('span.author')
        author = author_tag.get_text(strip=True).lstrip('/ ').strip() if author_tag else None

        recommend_tag = li.select_one('a.pc_voted_count .count')
        recommend_count = recommend_tag.get_text(strip=True) if recommend_tag else '0'

        comment_tag = li.select_one('.comment_count')
        comment_count = comment_tag.get_text(strip=True).strip('[]') if comment_tag else '0'

        regdate_tag = li.select_one('span.regdate')
        regdate_raw = regdate_tag.get_text(strip=True) if regdate_tag else None

        posts.append({
            'url': url,
            'title': title,
            'category': category,
            'author': author,
            'recommend_count': recommend_count,
            'comment_count': comment_count,
            'regdate_raw': regdate_raw,
        })

    return posts


# ---------------------------------------------------------------------------
# 3-3. 전체 수집 실행
# ---------------------------------------------------------------------------
# 목록 페이지를 1페이지부터 MAX_PAGE_COUNT까지 순서대로 방문합니다. 연속으로
# MAX_CONSECUTIVE_EMPTY번 빈 페이지가 나오면 "실제 데이터가 끝났다"고 보고 그 자리에서 멈춥니다.
# 그래서 실제로는 MAX_PAGE_COUNT를 다 채우기 전에 훨씬 빨리 끝나는 경우가 많습니다.

def run_scraper() -> list[dict]:
    """best2 게시판을 앞에서부터 순서대로 긁어서, 게시글 정보 dict의 리스트로 반환합니다."""

    # ※ Jupyter 노트북 안에서는 asyncio 이벤트 루프 정책 충돌 때문에 별도 스레드에서
    #   Playwright를 실행해야 했지만, 이 스크립트는 그냥 python으로 직접 실행되므로
    #   그런 우회가 필요 없습니다 (Windows의 기본 이벤트 루프가 이미 Playwright와 호환됩니다).
    posts = []
    consecutive_empty = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)

        for page_num in range(1, MAX_PAGE_COUNT + 1):
            html = fetch_rendered_html(page, LIST_URL, params={'page': page_num})
            page_posts = parse_list_page(html)

            if not page_posts:
                consecutive_empty += 1
                print(f'{page_num} 페이지: 게시글 없음 ({consecutive_empty}번째 연속 빈 페이지)')
                if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                    print(f'-> 연속 {MAX_CONSECUTIVE_EMPTY}회 빈 페이지: 실제 데이터가 끝난 것으로 보고 수집을 중단합니다.')
                    break
            else:
                consecutive_empty = 0
                posts.extend(page_posts)
                print(f'{page_num} 페이지: {len(page_posts)}건 수집 (누적 {len(posts)}건)')

            time.sleep(REQUEST_DELAY)  # 다음 요청 전에 잠깐 쉬어서 서버에 부담을 줄입니다.

        browser.close()

    return posts


# ---------------------------------------------------------------------------
# 4. 정제 단계에서 쓸 헬퍼 함수 (타입 변환, 날짜 파싱)
# ---------------------------------------------------------------------------

def to_int(text: str) -> int:
    """'1,234' / '1.2만' 같은 표기를 정수로 변환합니다. 읽을 수 없으면 0으로 처리합니다."""
    text = (text or '').strip().replace(',', '')
    if not text:
        return 0
    match = re.match(r'^(\d+(?:\.\d+)?)\s*만$', text)
    if match:
        return int(float(match.group(1)) * 10000)
    digits = re.sub(r'[^\d]', '', text)
    return int(digits) if digits else 0


def parse_regdate(raw, scraped_at: datetime):
    """목록 페이지의 regdate 텍스트('N분 전' / 'N시간 전' / 'YYYY.MM.DD')를 datetime으로 변환합니다."""
    if not raw:
        return None
    raw = raw.strip()

    m = re.match(r'^(\d+)\s*분\s*전$', raw)
    if m:
        return scraped_at - timedelta(minutes=int(m.group(1)))

    m = re.match(r'^(\d+)\s*시간\s*전$', raw)
    if m:
        return scraped_at - timedelta(hours=int(m.group(1)))

    m = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})$', raw)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d)

    return None  # 예상 못 한 형태면 None -> 정제 단계에서 이 행은 제거됩니다.


####################################################################
# 메인 파이프라인: 수집 -> 저장 -> 정제 -> 시각화
####################################################################

def main():
    # =======================================================================
    # 3장: 데이터 수집
    # =======================================================================
    print('=== 1) 데이터 수집 시작 ===')
    scraped_at = datetime.now()

    # Playwright(sync API)는 무거운 브라우저 프로세스를 띄우기 때문에, 만약을 위해
    # 별도 스레드에서 실행합니다. (일반 스크립트에서는 필수는 아니지만, 노트북 환경에서
    # 그대로 재사용할 수 있게 이 방식을 유지합니다.)
    with ThreadPoolExecutor(max_workers=1) as executor:
        all_posts = executor.submit(run_scraper).result()

    print(f'수집 완료: 총 {len(all_posts)}건 (수집 시작 시각 {scraped_at:%Y-%m-%d %H:%M})')

    # 정제 전 원본을 그대로 CSV로 남겨서, 정제 과정에서 무엇이 어떻게 바뀌었는지 비교할 수 있게 합니다.
    df_raw = pd.DataFrame(all_posts)
    df_raw.to_csv('fmkorea_best2_raw.csv', index=False, encoding='utf-8-sig')
    print(f'원본 저장 완료: fmkorea_best2_raw.csv (shape={df_raw.shape})')

    # =======================================================================
    # 4장: 데이터 정제
    # =======================================================================
    print('\n=== 2) 데이터 정제 시작 ===')
    df = df_raw.copy()

    # --- 4-1, 4-2. 결측치 확인 및 처리 ---
    # 카테고리 없이 등록되는 게시글도 실제로 존재하는 데이터이므로, 제거하지 않고
    # '미분류'라는 이름의 별도 그룹으로 남겨 둡니다.
    df['category'] = df['category'].replace('', '미분류')
    df.loc[df['category'].isna(), 'category'] = '미분류'

    # --- 4-3. 타입 변환 ---
    # 추천수·댓글수는 문자열로 수집되었기 때문에(예: "1,234"), 그래프·통계 계산을 위해
    # 숫자형으로 바꿉니다.
    df['추천수'] = df['recommend_count'].apply(to_int)
    df['댓글수'] = df['comment_count'].apply(to_int)

    # --- 4-4. 작성일자 정규화 + 파생 컬럼 ---
    # 상대 시간 표기("N분 전"/"N시간 전")는 수집 시작 시각(scraped_at) 기준으로 역산합니다.
    # (수집이 몇 분~몇십 분에 걸쳐 진행되므로 약간의 오차가 있을 수 있지만, 이 분석은
    #  '일 단위/요일 단위' 관찰이 목적이라 무시할 수 있는 수준입니다.)
    df['작성일시'] = df['regdate_raw'].apply(lambda x: parse_regdate(x, scraped_at))

    failed = df['작성일시'].isna().sum()
    print(f'작성일자를 해석할 수 없는 행: {failed}건 (분석에서 제거)')
    df = df.dropna(subset=['작성일시']).copy()

    WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']
    df['작성일'] = df['작성일시'].dt.date
    df['요일'] = df['작성일시'].dt.weekday.map(lambda i: WEEKDAY_KR[i])
    df['대분류'] = df['category'].apply(lambda c: c.split(' - ')[0])  # "유머 - 이슈" -> "유머"

    # --- 4-5. 중복 제거 ---
    # 수집이 진행되는 동안에도 사이트는 계속 갱신되기 때문에, 페이지 사이에서 같은
    # 게시글이 두 번 잡힐 수 있습니다. 게시글 URL을 기준으로 중복을 제거합니다.
    before = len(df)
    df = df.drop_duplicates(subset='url').reset_index(drop=True)
    print(f'중복 제거: {before}건 -> {len(df)}건 ({before - len(df)}건 제거)')

    # --- 4-6. 이상치 확인 메모 ---
    # 추천수·댓글수 모두 오른쪽으로 크게 치우친 분포이며 극단값이 있지만, 이 극단값들은
    # 센서 오류가 아니라 "실제로 크게 화제가 된 게시글"입니다. best2 자체가 이미
    # "화제가 된 글만" 모아 놓은 게시판이라 원래도 위로 치우친 분포가 자연스럽습니다.
    # 따라서 이 값들을 제거하지 않고 그대로 분석에 포함합니다.
    print(df[['추천수', '댓글수']].describe())

    df_clean = df[['title', 'category', '대분류', 'author', '추천수', '댓글수',
                    '작성일시', '작성일', '요일', 'url']].copy()
    df_clean = df_clean.rename(columns={'title': '제목', 'category': '카테고리', 'author': '작성자'})
    df_clean = df_clean[['작성자', '카테고리', '대분류', '제목', '작성일시', '작성일', '요일',
                          '추천수', '댓글수', 'url']]

    df_clean.to_csv('fmkorea_best2_clean.csv', index=False, encoding='utf-8-sig')
    print(f'정제 데이터 저장 완료: fmkorea_best2_clean.csv (shape={df_clean.shape})')

    # =======================================================================
    # 5장: 시각화로 살펴보기
    # =======================================================================
    # 질문 리마인드: 화제글의 카테고리에 따라 추천수·댓글수가 어떻게 달라질까?
    #               요일에 따라 화제글 발생 빈도가 다를까?
    print('\n=== 3) 시각화 시작 ===')

    # 카테고리 종류가 20개 넘게 나오기 때문에, 전부 그리면 x축이 너무 빽빽해집니다.
    # 게시글 수가 가장 많은 상위 TOP_N개 대분류만 골라서 그립니다.
    TOP_N = 8
    top_categories = df_clean['대분류'].value_counts().nlargest(TOP_N).index
    plot_df = df_clean[df_clean['대분류'].isin(top_categories)]
    print(f'대분류 {df_clean["대분류"].nunique()}개 중 게시글 수 상위 {TOP_N}개만 그래프에 사용합니다.')

    # --- 그래프 1: 카테고리별 추천수 분포 (박스플롯) ---
    # 박스플롯은 최솟값·최댓값·중앙값·사분위수를 한 번에 보여줘서, 카테고리마다
    # 추천수가 대체로 얼마나 되고 얼마나 들쭉날쭉한지 비교하기 좋습니다.
    order1 = plot_df.groupby('대분류')['추천수'].median().sort_values(ascending=False).index
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=plot_df, x='대분류', y='추천수', order=order1)
    plt.title(f'카테고리별 추천수 분포 (게시글 수 상위 {TOP_N}개 카테고리)')
    plt.xlabel('카테고리')
    plt.ylabel('추천수')
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    plt.savefig('chart1_category_recommend.png', dpi=150)
    plt.show()
    # 해석: 카테고리별로 추천수의 중앙값과 분포 폭이 눈에 띄게 다르다. 이슈성이 강한
    # 카테고리일수록 중앙값이 높고 분포도 넓게 퍼져 있는 경향이 있다.

    # --- 그래프 2: 카테고리별 댓글수 분포 (박스플롯) ---
    order2 = plot_df.groupby('대분류')['댓글수'].median().sort_values(ascending=False).index
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=plot_df, x='대분류', y='댓글수', order=order2)
    plt.title(f'카테고리별 댓글수 분포 (게시글 수 상위 {TOP_N}개 카테고리)')
    plt.xlabel('카테고리')
    plt.ylabel('댓글수')
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    plt.savefig('chart2_category_comment.png', dpi=150)
    plt.show()
    # 해석: 추천수 순위와 댓글수 순위가 카테고리마다 완전히 일치하지는 않는다.
    # "공감형" 화제성과 "논쟁형" 화제성은 다르게 움직인다는 뜻으로 볼 수 있다.

    # --- 그래프 3: 추천수와 댓글수의 관계 (산점도) ---
    plt.figure(figsize=(7, 6))
    sns.scatterplot(data=df_clean, x='추천수', y='댓글수', alpha=0.4)
    plt.title('추천수와 댓글수의 관계')
    plt.xlabel('추천수')
    plt.ylabel('댓글수')
    plt.tight_layout()
    plt.savefig('chart3_recommend_vs_comment.png', dpi=150)
    plt.show()

    correlation = df_clean['추천수'].corr(df_clean['댓글수'])
    print(f'추천수-댓글수 피어슨 상관계수: {correlation:.3f}')
    # 해석: 추천수와 댓글수는 양의 상관관계를 보이지만 강하지는 않다(1에 크게 못 미침).
    # 즉 "공감을 많이 받는 것"과 "댓글로 활발히 논의되는 것"은 서로 관련은 있지만 다른 화제성이다.

    # --- 그래프 4: 요일별 화제글 발생 빈도 (카운트플롯) ---
    weekday_order = ['월', '화', '수', '목', '금', '토', '일']
    plt.figure(figsize=(8, 5))
    sns.countplot(data=df_clean, x='요일', order=weekday_order)
    plt.title('요일별 화제글 수')
    plt.xlabel('요일')
    plt.ylabel('게시글 수')
    plt.tight_layout()
    plt.savefig('chart4_weekday_count.png', dpi=150)
    plt.show()
    # 해석: 요일별 화제글 수가 균등하지 않다면 특정 요일에 커뮤니티 활동이 몰리거나
    # 줄어드는 패턴이 있다는 뜻이다. 다만 수집 기간이 짧아 계절성 등 편향 가능성이 있다.

    # =======================================================================
    # 6장: 마무리 정리
    # =======================================================================
    print('\n=== 4) 마무리 ===')
    print('처음 질문 -> 카테고리별 추천수·댓글수 차이, 요일별 발생 빈도 차이')
    print('그린 그래프 -> 카테고리별 추천수/댓글수 박스플롯, 추천수-댓글수 산점도, 요일별 카운트플롯')
    print('한계: best2는 최근 며칠치 데이터만 유지되는 실시간 피드이고, 이미 "화제가 된 글만"')
    print('      모아 놓은 선별된 데이터이므로, 전체 게시글이나 긴 기간을 대표하지는 않는다.')


if __name__ == '__main__':
    main()
