# CLAUDE.md — 뉴스아카이빙 프로젝트

## 1. 프로젝트 개요

이커머스/유통 업계 뉴스를 RSS로 자동 수집하고, Claude API로 요약·분류·트렌드 도출 후 Notion과 이메일로 발송하는 자동화 파이프라인이다. GitHub Actions로 매주 월·수·금 오전 8시(KST)에 자동 실행된다.

---

## 2. 기술 스택 및 의존성

| 항목 | 상세 |
|---|---|
| Python | 3.12 |
| Claude API | `claude-haiku-4-5-20251001` (요약 + 트렌드 분석) |
| feedparser | RSS 수집 |
| notion-client | Notion 업로드 |
| resend | 이메일 발송 (HTML 뉴스레터) |
| python-dotenv | 로컬 환경변수 로드 |
| GitHub Actions | 스케줄 자동화 |

의존성 전체 목록: `requirements.txt`

---

## 3. 디렉토리 구조 및 핵심 파일 역할

```
뉴스아카이빙/
├── news_archiver.py          # 핵심 스크립트 — 전체 파이프라인 실행
├── requirements.txt          # pip 의존성
├── setup.sh                  # 최초 1회 설치 스크립트 (pip install + .env 생성)
├── .env                      # 로컬 환경변수 (git 제외)
├── .env.example              # 환경변수 템플릿
├── .gitignore                # .env, __pycache__ 등 제외
├── cron_setup.md             # 로컬 자동 실행 가이드 (Windows/macOS/Linux)
├── README.md                 # 프로젝트 설명 (인간용)
├── CLAUDE.md                 # 이 파일 (AI 어시스턴트용)
├── .github/
│   └── workflows/
│       └── daily_news.yml    # GitHub Actions 워크플로우
└── trends/
    ├── .gitkeep              # 빈 폴더 유지용
    └── trend_YYYY-MM-DD.txt  # 날짜별 리포트 (자동 생성)
```

### news_archiver.py 내부 구조

| 함수 | 역할 |
|---|---|
| `fetch_articles()` | RSS 피드 파싱, 4일 이내 기사만 수집 |
| `load_seen_records()` | 최근 4일 trends 파일에서 중복 URL·제목 추출 |
| `filter_duplicates()` | 수집된 기사 중 기존 리포트와 중복 제거 |
| `prioritize_and_limit()` | 국내 13개 + 글로벌 7개 쿼터로 우선순위 정렬 |
| `summarize_articles()` | Claude API 호출 — 한국어 제목·소카테고리·요약·시사점 생성 |
| `generate_insights()` | Claude API 호출 — 핵심 트렌드 3가지 도출 |
| `save_to_file()` | `trends/trend_YYYY-MM-DD.txt` 저장 |
| `upload_to_notion()` | Notion Database 또는 Page에 블록 업로드 |
| `_build_html()` | 이메일용 HTML 렌더링 |
| `send_email()` | Resend API로 TO + BCC 발송 |
| `main()` | 1~7단계 파이프라인 순차 실행 |

---

## 4. 환경변수 및 시크릿 설정

### 로컬 실행 (`.env` 파일)

`.env.example`을 복사해 `.env`를 만들고 값을 채운다.

```bash
cp .env.example .env
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `CLAUDE_API_KEY` | ✅ | Anthropic Claude API 키 |
| `NOTION_API_KEY` | 선택 | Notion Integration 토큰 |
| `NOTION_DATABASE_ID` | 선택 | Notion Database ID (방법 A — 신규 페이지 생성) |
| `NOTION_PAGE_ID` | 선택 | Notion 페이지 ID (방법 B — 기존 페이지에 추가) |
| `RESEND_API_KEY` | 선택 | Resend 이메일 API 키 |
| `EMAIL_FROM` | 선택 | 발신자 이메일 |
| `EMAIL_TO` | 선택 | 주 수신자 (쉼표 구분 다수 가능) |
| `EMAIL_BCC` | 선택 | BCC 수신자 (쉼표 구분 다수 가능) |
| `TRENDS_DIR` | 선택 | 리포트 저장 경로 (기본값: `./trends`) |

- `.env`는 `.gitignore`에 등록되어 있으므로 절대 커밋하지 않는다.
- `NOTION_DATABASE_ID`와 `NOTION_PAGE_ID`는 둘 중 하나만 설정해도 동작한다. 둘 다 설정하면 `NOTION_DATABASE_ID`가 우선된다.

### GitHub Actions (자동화 실행)

저장소 **Settings → Secrets and variables → Actions**에 아래 시크릿을 등록한다.

| Secret 이름 | 설명 |
|---|---|
| `GH_PAT` | GitHub Personal Access Token (push 권한 필요) |
| `CLAUDE_API_KEY` | Anthropic API 키 |
| `NOTION_API_KEY` | Notion Integration 토큰 |
| `NOTION_DATABASE_ID` | Notion Database ID |
| `RESEND_API_KEY` | Resend API 키 |
| `EMAIL_FROM` | 발신자 이메일 |
| `EMAIL_TO` | 주 수신자 이메일 |
| `EMAIL_BCC` | BCC 수신자 (쉼표 구분, 예: `a@ex.com,b@ex.com`) |

---

## 5. 로컬 실행 방법

```bash
# 최초 1회 — 의존성 설치 + .env 생성
bash setup.sh

# 일반 실행 (Notion 업로드 + 이메일 발송 포함)
python news_archiver.py

# 미리보기 모드 (파일 저장만, Notion·이메일 건너뜀)
python news_archiver.py --preview
```

실행 흐름 (7단계):
```
1/7  뉴스 수집 (RSS 피드 파싱)
2/7  중복 필터링 (최근 4일 비교)
3/7  우선순위 정렬 및 최대 20개 제한 (국내 13 + 글로벌 7)
4/7  Claude 요약 + 소카테고리 분류
5/7  핵심 트렌드 도출
6/7  파일 저장
7/7  Notion 업로드 + 이메일 발송
```

새 기사가 10개 미만이면(`MIN_NEW_ARTICLES = 10`) 발송 없이 정상 종료된다.

---

## 6. cron / 자동화 동작 방식

### GitHub Actions

- 파일: `.github/workflows/daily_news.yml`
- 스케줄: `cron: '0 23 * * 0,2,4'` → UTC 일/화/목 23:00 = KST 월/수/금 08:00
- 수동 실행: Actions 탭 → `이커머스/FMCG 뉴스 아카이빙` → **Run workflow**
- 실행 후 `trends/` 폴더 변경사항을 자동으로 `main` 브랜치에 커밋·푸시한다. 커밋 메시지 형식: `trend: YYYY-MM-DD 뉴스 리포트 자동 생성`

### 로컬 스케줄러

상세 설정은 `cron_setup.md` 참고.
- **Windows**: 작업 스케줄러 (PowerShell 또는 GUI)
- **macOS/Linux**: `crontab -e`
- **WSL2**: cron 데몬 시작 + crontab

---

## 7. 파일 네이밍 컨벤션

### trends/ 폴더

- 형식: `trend_YYYY-MM-DD.txt`
- 예시: `trend_2026-03-10.txt`
- 날짜는 KST 기준 (`Asia/Seoul`, UTC+9)
- `save_to_file()` 함수가 자동 생성하므로 수동으로 파일명을 만들 일은 없다.

### trends/ 파일 내부 구조

```
커머스 뉴스 트렌드 | YYYY-MM-DD
---

🔑 오늘의 핵심 트렌드

• (트렌드 1)
• (트렌드 2)
• (트렌드 3)

---
🇰🇷 국내 뉴스
---

[ 주요 플랫폼 ]

① 기사 제목
   출처: KR-쿠팡

   - 요약 불렛 1
   - 요약 불렛 2

   👉 시사점

   원문: https://...
---
```

소카테고리 출력 순서:
- 국내: 주요 플랫폼 → 플랫폼 → 배송/물류 → 마케팅 → 유한킴벌리 경쟁사 → 기타
- 글로벌: 플랫폼 → 배송/물류 → 마케팅 → 기타

---

## 8. 코드 수정 시 주의사항

### Claude API 모델
- 현재 모델: `claude-haiku-4-5-20251001`
- `summarize_articles()`와 `generate_insights()` 두 곳에서 호출한다. 모델을 바꿀 경우 두 곳 모두 수정해야 한다.

### 기사 쿼터
- 국내 최대: `KR_MAX = 13`, 글로벌 최대: `GL_MAX = 7` (합계 20개)
- 최소 발송 기준: `MIN_NEW_ARTICLES = 10` (미달 시 조용히 종료)

### RSS 피드 추가/수정
- `RSS_FEEDS` 리스트를 수정한다. 각 항목은 `label`, `region`, `url`, `max`(선택) 키를 가진다.
- `max`를 생략하면 `MAX_ARTICLES_PER_FEED = 10`이 기본값으로 적용된다.

### Notion 업로드 방식
- `NOTION_DATABASE_ID` 설정 시: 날짜별 신규 페이지 생성 (권장)
- `NOTION_PAGE_ID` 설정 시: 기존 페이지에 블록 추가
- 블록을 95개 단위로 나눠 업로드한다 (Notion API 한도 대응).

### 이메일 수신자
- `EMAIL_TO`, `EMAIL_BCC` 모두 쉼표로 구분하면 다수 지정 가능하다.
- 로컬에서는 `.env`, GitHub Actions에서는 Secrets에서 관리한다.

### 중복 필터링 기준
- 최근 4일 `trends/` 파일의 URL과 정규화 제목을 비교한다.
- `load_seen_records(days=4)` — `days` 값을 늘리면 더 오래된 기사도 중복 체크한다.

### --preview 플래그
- Notion 업로드와 이메일 발송을 건너뛰고 파일만 저장한다.
- 로컬 테스트 시 반드시 이 플래그를 사용해 API 과금과 실발송을 방지한다.

### 절대 수정하지 말아야 할 것
- `.gitignore`의 `.env` 항목 — 삭제 시 API 키가 GitHub에 노출된다.
- `daily_news.yml`의 `git push --force` 옵션 — Actions 봇 계정이 커밋하는 구조이므로 force push가 의도된 설계다.
