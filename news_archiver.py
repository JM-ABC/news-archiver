"""
이커머스/FMCG 뉴스 아카이버 v2
- 한국 + 글로벌 뉴스 RSS 수집 (11개 소스)
- Claude API로 요약 + 토픽 분류 + 시사점
- 핵심 트렌드 3가지 도출
- ~/trends/trend_YYYY-MM-DD.txt 저장 (인사이트 선행 포맷)
- Notion 페이지 업로드 (핵심 트렌드 + 토픽 그룹)
"""

import os
import sys
import re
import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import feedparser
import anthropic
import resend
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ────────────────────────────────────────────────────────────────────
CLAUDE_API_KEY     = os.getenv("CLAUDE_API_KEY")
NOTION_API_KEY     = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_PAGE_ID     = os.getenv("NOTION_PAGE_ID")
RESEND_API_KEY     = os.getenv("RESEND_API_KEY")
EMAIL_FROM         = os.getenv("EMAIL_FROM")          # 예: news@yourdomain.com
EMAIL_TO           = os.getenv("EMAIL_TO", "")        # 쉼표 구분 복수 가능

TRENDS_DIR = os.getenv("TRENDS_DIR", r"C:\Users\USER\Desktop\뉴스아카이빙\trends")
MAX_ARTICLES_PER_FEED = 5

# ── 헬퍼 ────────────────────────────────────────────────────────────────────
_CIRCLE = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩",
           "⑪","⑫","⑬","⑭","⑮","⑯","⑰","⑱","⑲","⑳",
           "㉑","㉒","㉓","㉔","㉕","㉖","㉗","㉘","㉙","㉚"]

def circle_num(n: int) -> str:
    return _CIRCLE[n - 1] if 1 <= n <= len(_CIRCLE) else f"({n})"

def _strip_md(text: str) -> str:
    """** ### 등 마크다운 기호 제거."""
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"#+\s*", "", text)
    return text.strip()

TOPIC_CATEGORIES = [
    "🚚 배송/물류",
    "🏪 플랫폼 경쟁",
    "🤖 AI/기술",
    "🌏 글로벌/해외",
    "🏬 오프라인유통",
    "🛒 FMCG/식품",
    "📊 기타",
]

# ── RSS 피드 목록 ──────────────────────────────────────────────────────────
RSS_FEEDS = [
    # ── 한국 (Google News 검색 RSS) ──────────────────────────────────────
    {
        "label": "KR-이커머스",
        "url": "https://news.google.com/rss/search?q=이커머스+쇼핑몰+온라인유통&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "label": "KR-FMCG-유통",
        "url": "https://news.google.com/rss/search?q=FMCG+소비재+편의점+마트+유통&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "label": "KR-쿠팡-네이버쇼핑",
        "url": "https://news.google.com/rss/search?q=쿠팡+네이버쇼핑+카카오쇼핑&hl=ko&gl=KR&ceid=KR:ko",
    },
    # ── 영문 Google News 검색 RSS ─────────────────────────────────────────
    {
        "label": "EN-eCommerce",
        "url": "https://news.google.com/rss/search?q=ecommerce+retail+trend&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "label": "EN-FMCG",
        "url": "https://news.google.com/rss/search?q=FMCG+consumer+goods+trend&hl=en-US&gl=US&ceid=US:en",
    },
    # ── 글로벌 전문 미디어 RSS ────────────────────────────────────────────
    {
        "label": "EN-RetailDive",
        "url": "https://www.retaildive.com/feeds/news/",
    },
    {
        "label": "EN-ModernRetail",
        "url": "https://www.modernretail.co/feed/",
    },
    {
        "label": "EN-GroceryDive",
        "url": "https://www.grocerydive.com/feeds/news/",
    },
    {
        "label": "EN-PYMNTS",
        "url": "https://www.pymnts.com/category/retail/feed/",
    },
    {
        "label": "EN-ChainStoreAge",
        "url": "https://chainstoreage.com/feed",
    },
    # ── 아시아 유통 (Google News) ──────────────────────────────────────────
    {
        "label": "ASIA-Retail",
        "url": "https://news.google.com/rss/search?q=Asia+retail+ecommerce+Amazon+Alibaba+Lazada&hl=en-US&gl=US&ceid=US:en",
    },
]


# ── 뉴스 수집 ────────────────────────────────────────────────────────────────
def fetch_articles() -> list[dict]:
    """RSS 피드에서 기사 수집. 중복 URL 제거 + 7일 이내 기사만 필터링."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

    articles = []
    seen_urls = set()
    skipped_old = 0

    for feed_info in RSS_FEEDS:
        print(f"  [수집] {feed_info['label']} ...")
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0
            for entry in feed.entries:
                if count >= MAX_ARTICLES_PER_FEED:
                    break
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue

                published = entry.get("published_parsed")
                if published:
                    pub_dt = datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc)
                    if pub_dt < cutoff:
                        skipped_old += 1
                        continue

                seen_urls.add(url)
                articles.append({
                    "title":    entry.get("title", "(제목 없음)"),
                    "title_ko": "",   # Claude가 채울 한국어 제목
                    "url":      url,
                    "source":   feed_info["label"],
                    "summary":  "",
                    "category": "📊 기타",
                    "insight":  "",
                })
                count += 1
        except Exception as e:
            print(f"  [오류] {feed_info['label']} 피드 실패: {e}")

    print(f"  총 {len(articles)}개 기사 수집 (7일 초과 {skipped_old}개 제외)")
    return articles


# ── Claude 요약 + 분류 ────────────────────────────────────────────────────────
def summarize_articles(articles: list[dict]) -> list[dict]:
    """Claude Haiku로 요약 + 토픽 분류 + 시사점 일괄 생성."""
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY 환경변수가 없습니다.")

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    titles_block = "\n".join(
        f"[{i+1}] ({a['source']}) {a['title']}" for i, a in enumerate(articles)
    )
    categories_str = " / ".join(TOPIC_CATEGORIES)

    prompt = f"""당신은 이커머스/FMCG 업계 현장을 잘 아는 시니어 MD 출신 블로거입니다.
아래 뉴스 기사 제목들을 읽고, 각 기사에 대해 다음 4가지를 작성하세요.

작성 규칙:
- 제목: 원문 기사 제목을 자연스러운 한국어로 번역 (한국어 기사는 원제목 그대로)
- 카테고리: 아래 목록 중 가장 적합한 것 하나만 선택 (이모지 포함하여 정확히 복사)
  {categories_str}
- 요약: 실무자(MD, 마케터, 사업기획자)에게 친근하고 부드러운 대화체 3문장 (예: "~이에요", "~거든요", "~인데요", "~일 것 같아요", bullet point 금지, ** ### 기호 절대 사용 금지)
- 시사점: MD/마케터가 오늘 당장 실행할 수 있는 행동 1문장, 친근한 어투 ("~해보세요", "~확인해보세요")
- 모든 출력은 한국어로 작성, ** ### 등 특수기호 절대 사용 금지

형식 (반드시 준수):
[번호]
제목: (한국어 제목)
카테고리: (카테고리명)
요약:
(3문장 산문)
시사점: (1문장)

기사 목록:
{titles_block}

각 [번호] 블록을 순서대로 작성하세요."""

    print("  [요약] Claude API 호출 중...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # 파싱: [1] ~ [N] 블록 분리
    blocks = re.split(r"\[(\d+)\]", raw)
    for i in range(1, len(blocks), 2):
        idx = int(blocks[i]) - 1
        if idx < 0 or idx >= len(articles):
            continue
        text = blocks[i + 1].strip() if i + 1 < len(blocks) else ""

        title_match = re.search(r"제목:\s*(.+)", text)
        if title_match:
            articles[idx]["title_ko"] = title_match.group(1).strip()
        else:
            articles[idx]["title_ko"] = articles[idx]["title"]

        cat_match = re.search(r"카테고리:\s*(.+)", text)
        if cat_match:
            articles[idx]["category"] = cat_match.group(1).strip()

        sum_match = re.search(r"요약:\s*([\s\S]+?)(?=\n시사점:|$)", text)
        if sum_match:
            articles[idx]["summary"] = sum_match.group(1).strip()
        else:
            fallback = re.sub(r"카테고리:.+\n?", "", text)
            fallback = re.sub(r"시사점:.+", "", fallback).strip()
            articles[idx]["summary"] = fallback

        ins_match = re.search(r"시사점:\s*(.+)", text)
        if ins_match:
            articles[idx]["insight"] = ins_match.group(1).strip()

    return articles


# ── 핵심 트렌드 도출 ─────────────────────────────────────────────────────────
def generate_insights(articles: list[dict]) -> list[str]:
    """전체 기사를 종합해 오늘의 핵심 트렌드 3가지 생성."""
    if not CLAUDE_API_KEY:
        return []

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    summaries_block = "\n".join(
        f"[{i+1}] ({a['category']}) {a['title']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""아래 뉴스 기사 목록을 보고, 오늘 이커머스/FMCG 업계 실무자가 꼭 알아야 할 핵심 트렌드 3가지를 작성하세요.

규칙:
- 각 트렌드는 1~2문장, 친근하고 부드러운 대화체 (예: "~이에요", "~거든요", "~인데요")
- 여러 기사를 종합한 통찰 (단순 기사 요약이 아닌 패턴/방향성)
- 실무적 시사점 포함
- ** ### 등 특수기호 절대 사용 금지
- 형식 반드시 준수

형식:
① (트렌드 1)
② (트렌드 2)
③ (트렌드 3)

기사 목록:
{summaries_block}"""

    print("  [인사이트] 핵심 트렌드 도출 중...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    trends = re.findall(r"[①②③]\s*(.+)", raw)
    return [_strip_md(t) for t in trends[:3]] if trends else [_strip_md(raw)]


# ── 파일 저장 ────────────────────────────────────────────────────────────────
def save_to_file(articles: list[dict], date_str: str, insights: list[str]) -> str:
    """~/trends/trend_YYYY-MM-DD.txt 에 인사이트 선행 포맷으로 저장."""
    os.makedirs(TRENDS_DIR, exist_ok=True)
    filepath = os.path.join(TRENDS_DIR, f"trend_{date_str}.txt")

    lines = [
        f"이커머스/FMCG 뉴스 트렌드 | {date_str}",
        "---",
        "",
        "🔑 오늘의 핵심 트렌드",
        "",
    ]
    for trend in insights:
        lines.append(_strip_md(trend))
    lines.append("")

    # 토픽별 그룹화 (TOPIC_CATEGORIES 순서 유지)
    grouped = defaultdict(list)
    for a in articles:
        grouped[a["category"]].append(a)

    ordered = [c for c in TOPIC_CATEGORIES if c in grouped]
    extra   = [c for c in grouped if c not in TOPIC_CATEGORIES]

    article_num = 1
    for cat in ordered + extra:
        lines += ["---", f"{cat}", "---", ""]
        for a in grouped[cat]:
            display_title = _strip_md(a.get("title_ko") or a["title"])
            lines += [f"{circle_num(article_num)} {display_title}", f"   출처: {a['source']}", ""]
            for line in a["summary"].splitlines():
                if line.strip():
                    lines.append(f"   {_strip_md(line.strip())}")
            if a.get("insight"):
                lines += ["", f"   💡 시사점: {_strip_md(a['insight'])}"]
            lines += ["", f"   URL: {a['url']}", "---", ""]
            article_num += 1

    lines.append(f"생성: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  [저장] {filepath}")
    return filepath


# ── Notion 헬퍼 ──────────────────────────────────────────────────────────────
def _make_rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _make_paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _make_rich_text(text)},
    }


def _make_divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _make_heading(text: str, level: int = 3) -> dict:
    h = f"heading_{level}"
    return {
        "object": "block",
        "type": h,
        h: {"rich_text": _make_rich_text(text)},
    }


def _make_callout(text: str, emoji: str = "💡") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _make_rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "yellow_background",
        },
    }


# ── Notion 업로드 ────────────────────────────────────────────────────────────
def upload_to_notion(articles: list[dict], date_str: str, insights: list[str]):
    """Notion에 날짜별 페이지 생성 또는 Database 행 추가."""
    if not NOTION_API_KEY:
        print("  [건너뜀] NOTION_API_KEY 없음")
        return

    notion = Client(auth=NOTION_API_KEY)

    blocks: list[dict] = [
        _make_heading(f"이커머스/FMCG 뉴스 트렌드 — {date_str}", level=2),
        _make_divider(),
    ]

    # 핵심 트렌드 섹션
    if insights:
        blocks.append(_make_heading("🔑 오늘의 핵심 트렌드", level=2))
        for trend in insights:
            blocks.append(_make_callout(_strip_md(trend)))
        blocks.append(_make_divider())

    # 토픽별 그룹화
    grouped = defaultdict(list)
    for a in articles:
        grouped[a["category"]].append(a)

    ordered = [c for c in TOPIC_CATEGORIES if c in grouped]
    extra   = [c for c in grouped if c not in TOPIC_CATEGORIES]

    article_num = 1
    for cat in ordered + extra:
        blocks.append(_make_heading(cat, level=2))
        for a in grouped[cat]:
            display_title = _strip_md(a.get("title_ko") or a["title"])
            blocks.append(_make_heading(f"{circle_num(article_num)} {display_title}", level=3))
            blocks.append(_make_paragraph(f"출처: {a['source']}"))
            for line in a["summary"].splitlines():
                if line.strip():
                    blocks.append(_make_paragraph(_strip_md(line.strip())))
            if a.get("insight"):
                blocks.append(_make_paragraph(f"💡 시사점: {_strip_md(a['insight'])}"))
            blocks.append(_make_paragraph(f"🔗 {a['url']}"))
            blocks.append(_make_divider())
            article_num += 1

    # ── Database 방식 ─────────────────────────────────────────────────────
    if NOTION_DATABASE_ID:
        print("  [Notion] Database에 새 페이지 생성 중...")
        chunk_size = 95
        page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={"Name": {"title": _make_rich_text(f"트렌드 리포트 {date_str}")}},
            children=blocks[:chunk_size],
        )
        for start in range(chunk_size, len(blocks), chunk_size):
            notion.blocks.children.append(
                page["id"],
                children=blocks[start: start + chunk_size],
            )
        print(f"  [Notion] 완료 → {page['url']}")
        return

    # ── 단일 페이지 방식 ──────────────────────────────────────────────────
    if NOTION_PAGE_ID:
        print("  [Notion] 기존 페이지에 블록 추가 중...")
        chunk_size = 95
        for start in range(0, len(blocks), chunk_size):
            notion.blocks.children.append(
                NOTION_PAGE_ID,
                children=blocks[start: start + chunk_size],
            )
        print("  [Notion] 완료")
        return

    print("  [건너뜀] NOTION_DATABASE_ID 또는 NOTION_PAGE_ID를 설정하세요.")


# ── 이메일 발송 ──────────────────────────────────────────────────────────────
def _build_html(articles: list[dict], date_str: str, insights: list[str]) -> str:
    """리포트를 HTML 이메일로 변환."""
    from collections import defaultdict

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    grouped = defaultdict(list)
    for a in articles:
        grouped[a["category"]].append(a)
    ordered = [c for c in TOPIC_CATEGORIES if c in grouped]
    extra   = [c for c in grouped if c not in TOPIC_CATEGORIES]

    # 핵심 트렌드
    trends_html = "".join(
        f"<p style='margin:6px 0;color:#1a1a1a;'>{esc(_strip_md(t))}</p>"
        for t in insights
    )

    # 기사 섹션
    sections_html = ""
    article_num = 1
    for cat in ordered + extra:
        articles_html = ""
        for a in grouped[cat]:
            display_title = esc(_strip_md(a.get("title_ko") or a["title"]))
            summary_html = "".join(
                f"<p style='margin:4px 0;'>{esc(_strip_md(line.strip()))}</p>"
                for line in a["summary"].splitlines() if line.strip()
            )
            insight_html = (
                f"<p style='margin:8px 0 0;color:#2563eb;'>"
                f"💡 {esc(_strip_md(a['insight']))}</p>"
                if a.get("insight") else ""
            )
            articles_html += f"""
            <div style='margin-bottom:24px;padding-bottom:24px;border-bottom:1px solid #e5e7eb;'>
              <p style='margin:0 0 4px;font-size:15px;font-weight:600;color:#111827;'>
                {circle_num(article_num)} {display_title}
              </p>
              <p style='margin:0 0 10px;font-size:12px;color:#6b7280;'>출처: {esc(a['source'])}</p>
              <div style='font-size:14px;color:#374151;line-height:1.7;'>{summary_html}</div>
              {insight_html}
              <p style='margin:8px 0 0;font-size:12px;'>
                <a href='{a["url"]}' style='color:#6b7280;'>원문 보기 →</a>
              </p>
            </div>"""
            article_num += 1

        sections_html += f"""
        <div style='margin-bottom:8px;'>
          <h2 style='margin:32px 0 12px;font-size:16px;font-weight:700;
                     color:#111827;border-bottom:2px solid #f3f4f6;padding-bottom:8px;'>
            {esc(cat)}
          </h2>
          {articles_html}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"></head>
<body style='margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'>
  <div style='max-width:640px;margin:32px auto;background:#fff;border-radius:12px;
              box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden;'>

    <!-- 헤더 -->
    <div style='background:#111827;padding:28px 32px;'>
      <p style='margin:0;font-size:12px;color:#9ca3af;letter-spacing:.05em;'>DAILY BRIEFING</p>
      <h1 style='margin:4px 0 0;font-size:22px;font-weight:700;color:#fff;'>
        이커머스/FMCG 뉴스 트렌드
      </h1>
      <p style='margin:6px 0 0;font-size:13px;color:#9ca3af;'>{date_str}</p>
    </div>

    <div style='padding:28px 32px;'>

      <!-- 핵심 트렌드 -->
      <div style='background:#fefce8;border-left:4px solid #eab308;
                  border-radius:4px;padding:16px 20px;margin-bottom:28px;'>
        <p style='margin:0 0 10px;font-size:13px;font-weight:700;color:#854d0e;
                  letter-spacing:.04em;'>🔑 오늘의 핵심 트렌드</p>
        {trends_html}
      </div>

      <!-- 기사 섹션 -->
      {sections_html}

    </div>

    <!-- 푸터 -->
    <div style='background:#f9fafb;padding:16px 32px;text-align:center;
                border-top:1px solid #e5e7eb;'>
      <p style='margin:0;font-size:11px;color:#9ca3af;'>
        자동 생성 · {date_str} · 이커머스/FMCG 뉴스 아카이버
      </p>
    </div>

  </div>
</body></html>"""


def send_email(articles: list[dict], date_str: str, insights: list[str]):
    """Resend로 HTML 뉴스 리포트 이메일 발송."""
    if not RESEND_API_KEY:
        print("  [건너뜀] RESEND_API_KEY 없음")
        return
    if not EMAIL_FROM or not EMAIL_TO:
        print("  [건너뜀] EMAIL_FROM 또는 EMAIL_TO 없음")
        return

    recipients = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]

    resend.api_key = RESEND_API_KEY
    html = _build_html(articles, date_str, insights)

    print(f"  [이메일] {len(recipients)}명에게 발송 중...")
    params: resend.Emails.SendParams = {
        "from":    EMAIL_FROM,
        "to":      recipients,
        "subject": f"[뉴스 리포트] 이커머스/FMCG 트렌드 | {date_str}",
        "html":    html,
    }
    result = resend.Emails.send(params)
    print(f"  [이메일] 완료 → id: {result.get('id', '-')}")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"\n▶ 뉴스 아카이빙 시작 [{date_str}]\n")

    print("1/5  뉴스 수집")
    articles = fetch_articles()
    if not articles:
        print("수집된 기사가 없습니다. 종료합니다.")
        sys.exit(1)

    print("\n2/5  Claude 요약 + 토픽 분류")
    articles = summarize_articles(articles)

    print("\n3/5  핵심 트렌드 도출")
    insights = generate_insights(articles)

    print("\n4/5  파일 저장")
    filepath = save_to_file(articles, date_str, insights)

    print("\n5/6  Notion 업로드")
    upload_to_notion(articles, date_str, insights)

    print("\n6/6  이메일 발송")
    send_email(articles, date_str, insights)

    print(f"\n✓ 완료! → {filepath}\n")


if __name__ == "__main__":
    main()
