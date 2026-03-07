# 커머스 뉴스 아카이버

이커머스/유통 업계 뉴스를 자동 수집·요약하고, Notion과 이메일로 발송하는 자동화 파이프라인입니다.

---

## 주요 기능

- **뉴스 수집**: Google News RSS 등 20여 개 피드에서 국내·글로벌 커머스 뉴스 수집
- **AI 요약**: Claude API로 각 기사를 소카테고리 분류 + 전문 분석가 시각의 요약 생성
- **핵심 트렌드**: 당일 뉴스를 종합한 핵심 트렌드 3가지 자동 도출
- **중복 필터링**: 최근 4일 리포트와 비교해 중복 기사 자동 제외
- **저장**: `trends/trend_YYYY-MM-DD.txt` 파일로 로컬 저장
- **Notion 업로드**: Database 또는 단일 페이지에 블록으로 업로드
- **이메일 발송**: Resend API로 HTML 뉴스레터 발송 (TO + BCC 지원)
- **자동 실행**: GitHub Actions로 매주 월·수·금 오전 8시(KST) 자동 실행

---

## 뉴스 커버리지

| 구분 | 대상 |
|---|---|
| 국내 주요 플랫폼 | 쿠팡, 네이버쇼핑, 컬리, G마켓, 11번가, 무신사, 올리브영, 이마트, 홈플러스, 롯데마트 등 |
| 국내 주제 | 이커머스 전략, AI커머스, 라이브커머스, 물류/배송, 패션/뷰티, 유통 정책, 소비 트렌드 |
| 글로벌 | Amazon, Walmart, Target, Temu, Shein, TikTok Shop, Shopee, JD.com 등 |
| 글로벌 미디어 | Retail Dive, Modern Retail, Grocery Dive, PYMNTS, Chain Store Age |

---

## 설치

### 1. 저장소 클론

```bash
git clone https://github.com/{username}/{repo}.git
cd 뉴스아카이빙
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `CLAUDE_API_KEY` | ✅ | Anthropic Claude API 키 |
| `NOTION_API_KEY` | 선택 | Notion Integration 토큰 |
| `NOTION_DATABASE_ID` | 선택 | Notion Database ID (방법 A) |
| `NOTION_PAGE_ID` | 선택 | Notion 페이지 ID (방법 B) |
| `RESEND_API_KEY` | 선택 | Resend 이메일 발송 API 키 |
| `EMAIL_FROM` | 선택 | 발신자 이메일 |
| `EMAIL_TO` | 선택 | 수신자 이메일 (쉼표로 다수 지정) |
| `EMAIL_BCC` | 선택 | BCC 이메일 (쉼표로 다수 지정) |

---

## 실행

### 일반 실행 (Notion 업로드 + 이메일 발송 포함)

```bash
python news_archiver.py
```

### 미리보기 모드 (파일 저장만, Notion·이메일 건너뜀)

```bash
python news_archiver.py --preview
```

---

## 자동 실행 설정

### GitHub Actions (권장)

저장소 Settings → Secrets에 환경변수를 등록하면 매주 **월·수·금 오전 8시(KST)** 자동 실행됩니다.
수동 실행은 Actions 탭 → `이커머스/FMCG 뉴스 아카이빙` → **Run workflow** 버튼을 사용합니다.

### 로컬 자동 실행

자세한 설정 방법은 [cron_setup.md](cron_setup.md)를 참고하세요.

- **Windows**: 작업 스케줄러 (PowerShell 또는 GUI)
- **macOS / Linux**: crontab
- **WSL2**: cron 데몬 + crontab

---

## 출력 구조

```
trends/
└── trend_2026-03-01.txt   # 날짜별 리포트
```

리포트 내용:
1. 🔑 오늘의 핵심 트렌드 (3가지)
2. 🇰🇷 국내 뉴스 (주요 플랫폼 / 플랫폼 / 배송·물류 / 마케팅 / 유한킴벌리 경쟁사 / 기타)
3. 🌎 글로벌 뉴스 (플랫폼 / 배송·물류 / 마케팅 / 기타)

---

## 실행 흐름

```
1/7  뉴스 수집 (RSS 피드 파싱)
2/7  중복 필터링 (최근 4일 비교)
3/7  우선순위 정렬 및 최대 20개 제한 (국내 13 + 글로벌 7)
4/7  Claude 요약 + 소카테고리 분류
5/7  핵심 트렌드 도출
6/7  파일 저장
7/7  Notion 업로드 + 이메일 발송
```

---

## 기술 스택

- **Python 3.12**
- **Claude API** (claude-haiku-4-5) — 요약 및 트렌드 분석
- **feedparser** — RSS 수집
- **notion-client** — Notion 업로드
- **resend** — 이메일 발송
- **GitHub Actions** — 스케줄 자동화
