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
- 스케줄: `cron: '43 21 * * 0,2,4'` → UTC 일/화/목 21:43 = KST 월/수/금 06:43 (GitHub Actions 예약 실행 지연이 잦아 — 2026-08-28 이후 최대 7시간 46분까지 지연된 사례 확인됨 — 실제 도착이 오전 8시 근처에 맞도록 목표 시각을 앞당겼다. 정각/정시(`:00`, `:30`)는 GitHub Actions가 몰리는 시간대라 피함)
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
- 국내 최대: `KR_MAX = 12`, 글로벌 최대: `GL_MAX = 10` (합계 22개)
- 최소 발송 기준: `MIN_NEW_ARTICLES = 10` (미달 시 조용히 종료)

### RSS 피드 추가/수정
- `RSS_FEEDS` 리스트를 수정한다. 각 항목은 `label`, `region`, `url`, `max`(선택), `trusted_only`(선택) 키를 가진다.
- `max`를 생략하면 `MAX_ARTICLES_PER_FEED = 10`이 기본값으로 적용된다.

주의할 점 (구글 뉴스 검색어):
- **구글 뉴스는 공백(`+`)을 AND로 해석한다.** `q=Amazon+Walmart+Target+retail`은 "네 단어가 모두 들어간 기사"를 찾으므로 사실상 0건이다. 2026-09-14 점검 시 이 형태의 피드 약 20개가 수개월간 0건이었다 (`GL-메가유통`, `KR-이커머스`, `KR-물류택배` 등).
- 여러 브랜드를 받으려면 **브랜드별로 피드를 나눈다** (국내 `KR-쿠팡` 등과 같은 구조). `OR`(`q=Temu+OR+Shein`)도 동작하지만, 주제어를 OR로 묶으면 노이즈가 크다 (예: `택배 OR 물류센터` → "뇌세포 RNA 택배").
- 영문 브랜드명만 넣으면 소비자 가십이 쏟아진다 (`Costco` → 할인 상품·매장 목격담). `Amazon+ecommerce`처럼 업계 맥락어를 AND로 붙인다.
- 피드를 추가·수정한 뒤에는 4일 이내 기사가 실제로 몇 건 나오는지 확인한다. 전체 건수가 많아도 전부 오래된 기사일 수 있다.
- 2026-09-16: 남아 있던 AND 형태 피드를 정리했다. `KR-이커머스`는 `이커머스+시장`으로, `KR-물류택배`는 `KR-새벽배송`·`KR-풀필먼트` 두 피드로 나눴고, `GL-Shopify`는 `Shopify+ecommerce`로 좁히며 `trusted_only`를 걸었다.
- `GL-버티컬`(Etsy·Wayfair·Chewy)은 삭제했다. 브랜드별로 나눠도 4일 이내 유효 기사가 0건이다 — Etsy는 증권사 목표주가 리포트, Wayfair는 세일 광고, Chewy는 반려동물 가십만 나온다. **브랜드별 분리가 항상 답은 아니다.** 그 브랜드가 업계 뉴스를 만들어내는지 먼저 확인한다.
- 주제어 피드는 같은 사건을 여러 매체가 받아쓰는 비율이 높다 (`풀필먼트` 65건 중 상위 12건이 전부 한진 영국 센터 기사). `max`를 2~3으로 낮게 잡는다.

### 글로벌 신뢰 매체 허용 목록
- `"trusted_only": True`인 피드는 `GL_TRUSTED_DOMAINS`에 있는 도메인의 기사만 받는다. 현재 글로벌 브랜드 구글 뉴스 피드(Amazon·Walmart·Target·Costco·Temu/Shein·TikTok Shop·Shopify)에만 적용한다.
- 이유: 영문 구글 뉴스는 브랜드가 언급되면 매체를 가리지 않는다. 차단 목록으로는 저품질 매체가 끝없이 나타난다 (2026-09-14: upi.com, EcommerceBytes, finance.biggo.com).
- 광고 매체 차단과 같은 위치(날짜 필터 뒤, `count` 증가 앞)에서 검사하므로, 제외된 자리는 같은 피드의 다음 기사가 채운다.
- 제외된 기사는 로그에 `신뢰 매체 외 제외`로 출력된다. 좋은 매체가 반복해서 보이면 `GL_TRUSTED_DOMAINS`에 한 줄 추가한다.
- 서브도메인은 자동 허용하지 않는다 (`markets.businessinsider.com`은 보도자료 게시판).
- 매체가 좋아도 주제가 약한 기사(예: 블룸버그의 소액 합의금 기사)는 못 거른다. 이런 건 Claude 자체 판정 제외(`filter_self_excluded`)가 맡는다.

### Claude 자체 판정 제외
- Claude가 시사점에 "파급력은 제한적" 같은 문구를 쓰면 `filter_self_excluded()`가 그 기사를 뺀다.
- 키워드는 **조사(은/는/이/가)를 무시하고** 비교한다. Claude가 같은 뜻을 `파급력은`/`파급력이`로 바꿔 쓰기 때문이다 (2026-09-14: 조사 한 글자 차이로 5건 통과).
- 표현 자체가 다른 경우("별개의 사건 뉴스입니다", "파급력 분석이 제한적")는 아직 못 잡는다. 이런 문구는 대부분 "이 항목은"으로 시작한다.

### 핵심 트렌드가 없을 때
- 트렌드를 못 뽑으면 **트렌드 섹션 없이 발송한다.** Claude 답변 원문을 트렌드 자리에 넣으면 안 된다 (2026-09-25: "트렌드를 도출하기 어렵습니다… 권고사항" 설명문이 1번 트렌드로 발송됨).
- `_parse_trends()`는 `▶` 블록만 트렌드로 인정하고, "도출하기 어렵" 같은 해명 문구가 든 블록은 버린다. 결과가 비면 한 번 더 요청하고, 그래도 비면 빈 목록을 돌려준다.
- 프롬프트는 "3~5개"가 아니라 "1~5개"다. 3개를 강제하면 Haiku가 개수를 못 채울 때 아예 포기한다.

### 카톡 발송 승인 (슬랙 / PC 팝업)
- `kakao_notify.py`는 발송 전 반드시 사람 승인을 받는다. 오픈채팅방은 오발송을 되돌릴 수 없다.
- `SLACK_BOT_TOKEN`과 `SLACK_APPROVAL_CHANNEL`이 설정돼 있으면 슬랙 스레드 답글로 승인받고, 비어 있으면 기존 PC 팝업(tkinter)으로 떨어진다. 슬랙 호출이 중간에 실패해도 팝업으로 내려온다 — 어차피 PC가 켜져 있어야 발송되는 구조라 팝업이 마지막 방어선으로 남는 편이 낫다.
- 승인은 답글 **전체 일치**로만 인정한다 (`발송`, `ㅇㅇ`, `ok`). 부분 일치로 처리하면 "발송하지마"가 승인으로 읽혀 정반대로 동작한다.
- `SLACK_APPROVER_USER_ID`를 비워두면 채널의 누구나 승인할 수 있다. 본인 ID를 넣어두는 편이 안전하다.
- 슬랙 버튼(Block Kit)은 클릭을 받아줄 공개 URL이 있어야 해서 쓰지 않았다. 답글 폴링(5초 간격)이 서버 없이 되는 방식이다.
- 시간 초과(기본 30분)는 항상 "취소"다. 기본값이 "안 보냄"이라는 원칙은 유지한다.
- `python kakao_notify.py --test-approval` — 승인 경로만 시험한다 (실제 카톡 발송 없음). 슬랙 설정을 바꾼 뒤에는 이걸로 먼저 확인한다. 단위 테스트는 슬랙 API 응답 형태까지 검증하지 못한다.
- `python kakao_notify.py --test-paste` — 실제 채팅방 입력창에 붙여넣고 원본과 비교한 뒤 Enter 없이 비운다. 붙여넣기 검증 실패가 나면 이걸로 재현한다. 실패 시 로그에 몇 번째 글자부터 달라졌는지 남는다.
- 승인 채널: `#커머스-카톡승인` (비공개, 2026-09-30부터). 봇(Demo App)이 채널 멤버여야 한다.
- **봇은 동시에 하나만 돈다** (윈도우 이름 있는 뮤텍스). 2026-09-30에 예약 실행(11:20:00)과 수동 실행(11:20:01)이 겹쳐 카톡이 두 번 나갔다 — 채널에 친 `발송` 한 번이 두 승인 요청을 모두 승인했기 때문이다. 승인 뒤 전송 직전에도 `already_sent()`를 다시 확인한다.
- **봇 PC 화면이 잠겨 있으면 전송할 수 없다.** 화면 조작 방식이라 잠금 중에는 입력창이 "메시지 입력"(안내문구)으로만 읽힌다. 2026-10-02에 다른 노트북에서 슬랙 승인을 눌렀는데 이 때문에 실패했다(9/30 11:06~11:08도 같은 증상, 원인은 미확인). `is_screen_locked()`가 승인 요청 시점에 슬랙 메시지 맨 위로 경고하고, 승인 뒤 전송 직전에 다시 확인해 잠겨 있으면 슬랙 채널 + 이메일로 알리고 전송을 시도하지 않는다. 잠금 상태 감지는 실제 잠금으로 검증하지 못했다 — 단위 테스트는 가짜 user32로만 돈다.
- 수동 실행 전에는 작업 스케줄러 `커머스카톡봇`의 다음 실행 시각을 확인한다. 월·수·금 08:20부터 30분 간격으로 11:20까지 반복하고, 놓친 실행은 PC가 깨어나면 바로 돈다 (`StartWhenAvailable`).

### Notion 업로드 방식
- `NOTION_DATABASE_ID` 설정 시: 날짜별 신규 페이지 생성 (권장)
- `NOTION_PAGE_ID` 설정 시: 기존 페이지에 블록 추가
- 블록을 95개 단위로 나눠 업로드한다 (Notion API 한도 대응).

### 이메일 수신자
- `EMAIL_TO`, `EMAIL_BCC` 모두 쉼표로 구분하면 다수 지정 가능하다.
- 로컬에서는 `.env`, GitHub Actions에서는 Secrets에서 관리한다.

### 광고성 기사 차단 (2단 구조)

1. **매체 차단** — `BLOCKED_PUBLISHERS`(매체명) / `BLOCKED_DOMAINS`(도메인). Google News RSS의 `<source>`에서 발행 매체를 읽어 수집 단계에서 제외한다. 광고 단어 없는 낚시성 제목(예: "상담 10건 중 7건은 같은 이야기")은 제목 패턴으로 잡히지 않으므로 이 장치가 필요하다.
2. **제목 패턴 차단** — `_AD_PATTERNS` 정규식 → `filter_ad_articles()`.

새 광고 매체를 막으려면 `BLOCKED_PUBLISHERS`에 매체명 한 줄만 추가하면 된다. 차단된 기사는 실행 로그에 `매체명: 제목` 형태로 출력되므로 오탐 여부를 GitHub Actions 로그에서 확인할 수 있다.

주의할 점:
- 매체 차단은 **날짜 필터 뒤, `count` 증가 앞**에 위치한다. 순서를 바꾸면 오래된 기사까지 로그에 쌓이거나(앞으로 이동), 광고 기사가 피드별 `max` 쿼터를 잡아먹는다(뒤로 이동).
- Google News 검색 쿼리에 `-site:` 연산자를 쓰면 안 된다. 뉴스 검색 모드가 해제되면서 나무위키·티스토리 같은 일반 웹 결과가 섞여 들어온다.
- `_AD_PATTERNS`에 흔한 단어를 단독으로 넣으면 정상 기사를 잡는다. 예: `총정리`는 "전자상거래법 개정안 총정리"를 걸러버려 `(방법|노하우|비법|꿀팁)\s*총정리`로 좁혔다.
- "네이버 프리미엄콘텐츠"와 "브런치"는 의도적으로 차단하지 않는다. 실적·재무 분석 등 볼 만한 글이 섞여 있다.
- 아이보스 칼럼은 전면 차단해도 손실이 없다. Google News가 칼럼 게시판을 뉴스로 색인하지 않아 RSS 표본 249건 중 0건이었고, 색인되는 건 판매·홍보 게시판 글뿐이다. 게시판 단위 선별도 불가능하다 — 색인된 글의 74%는 제목에 게시판 표시가 없다.

### 중복 필터링 기준
- 최근 3일 `trends/` 파일의 URL과 정규화 제목을 비교한다.
- `load_seen_records(days=3)` — `days` 값을 늘리면 더 오래된 기사도 중복 체크한다.

### --preview 플래그
- Notion 업로드와 이메일 발송을 건너뛰고 파일만 저장한다.
- 로컬 테스트 시 반드시 이 플래그를 사용해 API 과금과 실발송을 방지한다.

### 절대 수정하지 말아야 할 것
- `.gitignore`의 `.env` 항목 — 삭제 시 API 키가 GitHub에 노출된다.
- `daily_news.yml`의 `git push --force` 옵션 — Actions 봇 계정이 커밋하는 구조이므로 force push가 의도된 설계다.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
