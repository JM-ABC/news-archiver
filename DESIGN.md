# Commerce Briefing — 이메일 디자인 시스템

이 문서는 `_build_html()` 계열 함수가 생성하는 HTML 이메일의 디자인 토큰·컴포넌트·원칙을 정의합니다.
코드 상수와 1:1 대응되므로, 디자인을 바꿀 때는 코드와 이 문서를 함께 수정합니다.

---

## 1. 색상 토큰

| 상수 | 값 | 용도 |
|---|---|---|
| `_COLOR_DARK` | `#0C0C0C` | 헤더 배경, 지역 섹션 헤더 텍스트·보더 |
| `_COLOR_DARK_ALT` | `#1A1A1A` | 핵심 트렌드 strip 배경 |
| `_COLOR_GOLD` | `#C8B870` | 주 액센트 — 트렌드 타이틀, 기사 번호, 인사이트 보더, 레이블 |
| `_COLOR_BG` | `#EDEAE2` | 이메일 외부 배경 (웜 오프화이트) |
| `_COLOR_FOOTER` | `#F8F6F0` | 푸터 배경, 인사이트 callout 배경 |

### 보조 색상 (상수 미지정, 직접 사용)

| 값 | 용도 |
|---|---|
| `#FFFFFF` | 기사 본문 영역 배경 |
| `#111111` | 기사 제목 텍스트 |
| `#666666` | 요약 불렛 텍스트 |
| `#374151` | 인사이트 callout 텍스트 |
| `#AAAAAA` | 기사 수(`N건`), 푸터 텍스트 |
| `#999999` | "원문 보기 →" 링크 |
| `#F0F0F0` | 기사 간 구분선 |
| `#DDDDDD` | 푸터 상단 보더 |

---

## 2. 소카테고리 태그 색상

`_TAG_COLORS` 딕셔너리 정의. 배경/전경 쌍.

| 소카테고리 | 배경 | 전경 |
|---|---|---|
| 플랫폼 | `#EBF4FF` | `#1A6BB5` |
| 배송/물류 | `#FEF3E2` | `#A06010` |
| 마케팅 | `#FFEDEC` | `#B83030` |
| 유한킴벌리 경쟁사 | `#F5EDF8` | `#7B3FA0` |
| 기타 | `#F3F4F6` | `#6B7280` |

새 소카테고리 추가 시 `_TAG_COLORS`에 항목을 추가하면 자동 적용됩니다.

---

## 3. 타이포그래피

| 상수 | 폰트 스택 | 용도 |
|---|---|---|
| `_HTML_S` | Georgia → Times New Roman → Apple SD Gothic Neo → Malgun Gothic → sans-serif | 헤드라인 "Commerce Briefing" (36px/30px 모바일), 트렌드 번호·제목, 기사 제목(13px) |
| `_HTML_A` | Arial → Helvetica → sans-serif | 레이블(11px), 메타, 요약 불렛, 인사이트, 푸터 등 본문 전반 |

> **참고:** `_HTML_S`는 영문에 Georgia, 한글에 Apple SD Gothic Neo(macOS) / Malgun Gothic(Windows)를 명시해 명조 계열 폰트(바탕체) 렌더링을 방지합니다. `_HTML_A`는 한글·영문 모두 sans-serif 계열로 렌더링됩니다.

---

## 4. 레이아웃

- **최대 너비:** 600px (이메일 클라이언트 표준)
- **외부 여백:** 좌우 16px, 상하 28px
- **내부 좌우 패딩:** 24px (헤더·본문·푸터 공통)
- **테이블 기반 레이아웃:** 모든 구조는 `role="presentation"` 테이블 사용 (Outlook 호환)

---

## 5. 컴포넌트

### 5-1. 헤더

```
배경: _COLOR_DARK (#0C0C0C)
패딩: 32px 24px 24px 24px

상단 행: 레이블(금색, 11px, 0.14em 자간, uppercase) | 날짜(회색, 11px)
제목:    "Commerce Briefing" (_HTML_S, 36px, bold, #111111, -0.02em 자간) — Georgia(macOS/iOS) / Times New Roman(Windows)
부제:    "AI-curated · Delivered Mon · Wed · Fri" (_HTML_A, 11px, #666666)
```

### 5-2. 핵심 트렌드 Strip

```
배경: _COLOR_DARK_ALT (#1A1A1A)
레이블: "오늘의 핵심 트렌드" (금색, 11px, uppercase, 패딩 18px 24px 12px)

트렌드 블록 (반복):
  - 첫 번째: border-left 3px _COLOR_GOLD, 배경 #222222
  - 이후:    border-left 3px #888888, 배경 #1E1E1E
  - 제목:    bold, 15px (첫 번째 금색 / 이후 #AAAAAA)
  - 본문:    14px (첫 번째 #F0F0F0 / 이후 #CCCCCC)

insights 빈 경우: strip 전체 숨김
```

### 5-3. 기사 카드

```
번호:     금색(_COLOR_GOLD), 11px bold, 너비 32px, 상단 정렬
태그:     소카테고리 pill + 소스 pill (2px 8px 패딩, 11px bold)
제목:     _HTML_S, 15px bold, #111111, word-break:break-word
불렛:     · 접두어, _HTML_A, 14px, #666666, 1.7 행간
인사이트: 배경 _COLOR_FOOTER, border-left 2px _COLOR_GOLD, 14px, #374151
링크:     "원문 보기 →", 11px, #999999, display:inline-block, padding:6px 0
```

### 5-4. 푸터

```
배경: _COLOR_FOOTER (#F8F6F0)
보더: border-top 1px #DDDDDD
텍스트: "자동 생성 · {날짜} · 커머스 뉴스 아카이버" (11px, #AAAAAA)
수신거부: EMAIL_UNSUBSCRIBE_URL 설정 시만 표시 (11px, #CCCCCC)
```

---

## 6. 이메일 특화 규칙

- **Preheader:** `<body>` 직후 숨김 div로 첫 트렌드 제목 삽입 → inbox 미리보기 텍스트
- **인라인 CSS 전용:** 이메일 클라이언트 CSS 변수 지원 불안정 → Python 상수로 관리
- **MSO 조건부 주석:** Outlook 렌더링을 위한 `<!--[if gte mso 9]>` 블록 유지
- **Outlook 테이블 초기화:** `mso-table-lspace:0pt; mso-table-rspace:0pt` 필수
- **모바일 미디어쿼리:** `max-width:480px` 시 헤드라인 30px (현재 단일 규칙)

---

## 7. 디자인 원칙

1. **에디토리얼 우선** — 다크 헤더 + 금색 액센트로 고급 뉴스레터 느낌 유지. 플래시하지 않게.
2. **AI slop 금지** — 이모지를 디자인 요소로 사용 금지, 장식적 색상 보더 최소화.
3. **스캔 가능성** — 기사 번호(01·02…), 지역 구분, 소카테고리 태그로 빠른 스캔 지원.
4. **색상 변경은 상수에서** — `_COLOR_*` 상수와 `_TAG_COLORS`만 수정하면 전체 적용.
5. **다크모드 defer** — 이메일 클라이언트별 지원 편차가 커 현재 스코프 밖.
