"""
커머스 뉴스 아카이버 v3
- 대카테고리: 🇰🇷 국내 뉴스 / 🌎 글로벌 뉴스
- 소카테고리: 주요 플랫폼 / 플랫폼 / 배송·물류 / 마케팅 / 유한킴벌리 경쟁사 / 기타
- RSS 12개 소스, 최대 20개 기사 (주요 플랫폼 우선)
- Claude API: 불렛포인트 요약 + 지역/소카테고리 분류 + 시사점
- ~/trends/trend_YYYY-MM-DD.txt 저장
- Notion Database 업로드 / Resend 이메일 발송
- --preview 플래그: Notion·이메일 건너뛰고 파일만 저장 후 stdout 출력
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
EMAIL_FROM         = os.getenv("EMAIL_FROM")
EMAIL_TO           = os.getenv("EMAIL_TO", "")
TRENDS_DIR         = os.getenv("TRENDS_DIR", r"C:\Users\USER\Desktop\뉴스아카이빙\trends")

MAX_ARTICLES_PER_FEED = 8
MIN_NEW_ARTICLES      = 10
MAX_TOTAL_ARTICLES    = 20
PREVIEW               = "--preview" in sys.argv

# 주요 플랫폼 우선순위 키워드
PRIORITY_KEYWORDS = ["쿠팡", "네이버", "컬리", "올리브영"]

# 대카테고리
REGION_KR = "🇰🇷 국내 뉴스"
REGION_GL = "🌎 글로벌 뉴스"
REGIONS   = [REGION_KR, REGION_GL]

# 소카테고리 (출력 순서)
KR_SUBCATS = ["주요 플랫폼", "플랫폼", "배송/물류", "마케팅", "유한킴벌리 경쟁사", "기타"]
GL_SUBCATS = ["플랫폼", "배송/물류", "마케팅", "기타"]

# ── RSS 피드 ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # 한국
    {"label": "KR-이커머스",   "region": REGION_KR,
     "url": "https://news.google.com/rss/search?q=이커머스+쇼핑몰+온라인유통&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-FMCG",      "region": REGION_KR,
     "url": "https://news.google.com/rss/search?q=FMCG+소비재+편의점+마트+유통&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-주요플랫폼", "region": REGION_KR,
     "url": "https://news.google.com/rss/search?q=쿠팡+네이버쇼핑+마켓컬리+올리브영&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-유한킴벌리", "region": REGION_KR,
     "url": "https://news.google.com/rss/search?q=화장지+생리대+기저귀+물티슈+유아스킨케어+유한킴벌리+깨끗한나라&hl=ko&gl=KR&ceid=KR:ko"},
    # 영문 Google News
    {"label": "EN-eCommerce",   "region": REGION_GL,
     "url": "https://news.google.com/rss/search?q=ecommerce+retail+trend&hl=en-US&gl=US&ceid=US:en"},
    {"label": "EN-FMCG",        "region": REGION_GL,
     "url": "https://news.google.com/rss/search?q=FMCG+consumer+goods+trend&hl=en-US&gl=US&ceid=US:en"},
    # 글로벌 전문 미디어
    {"label": "EN-RetailDive",    "region": REGION_GL, "url": "https://www.retaildive.com/feeds/news/"},
    {"label": "EN-ModernRetail",  "region": REGION_GL, "url": "https://www.modernretail.co/feed/"},
    {"label": "EN-GroceryDive",   "region": REGION_GL, "url": "https://www.grocerydive.com/feeds/news/"},
    {"label": "EN-PYMNTS",        "region": REGION_GL, "url": "https://www.pymnts.com/category/retail/feed/"},
    {"label": "EN-ChainStoreAge", "region": REGION_GL, "url": "https://chainstoreage.com/feed"},
    # 아시아
    {"label": "ASIA-Retail",      "region": REGION_GL,
     "url": "https://news.google.com/rss/search?q=Asia+retail+ecommerce+Amazon+Alibaba+Lazada&hl=en-US&gl=US&ceid=US:en"},
]

# ── 헬퍼 ────────────────────────────────────────────────────────────────────
_CIRCLE = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩",
           "⑪","⑫","⑬","⑭","⑮","⑯","⑰","⑱","⑲","⑳",
           "㉑","㉒","㉓","㉔","㉕","㉖","㉗","㉘","㉙","㉚"]

def circle_num(n: int) -> str:
    return _CIRCLE[n - 1] if 1 <= n <= len(_CIRCLE) else f"({n})"

def _strip_md(text: str) -> str:
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"#+\s*", "", text)
    return text.strip()

def _normalize_title(title: str) -> str:
    return re.sub(r"[^\w가-힣]", "", title.lower())


# ── 중복 필터링 ───────────────────────────────────────────────────────────────
def load_seen_records(days: int = 7) -> tuple[set[str], set[str]]:
    """최근 N일 trends 파일에서 URL과 정규화 제목 추출."""
    seen_urls, seen_titles = set(), set()
    for i in range(1, days + 1):
        date = datetime.date.today() - datetime.timedelta(days=i)
        fp = os.path.join(TRENDS_DIR, f"trend_{date}.txt")
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                content = f.read()
            # 구버전(URL:)과 신버전(원문:) 모두 지원
            for url in re.findall(r"(?:URL|원문):\s*(https?://\S+)", content):
                seen_urls.add(url.strip())
            for line in content.splitlines():
                m = re.match(r"[①-⑳㉑-㉚]\s+(.+)", line.strip())
                if m:
                    seen_titles.add(_normalize_title(m.group(1)))
        except Exception:
            pass
    print(f"  최근 {days}일 기록: URL {len(seen_urls)}개, 제목 {len(seen_titles)}개")
    return seen_urls, seen_titles


def filter_duplicates(articles: list[dict],
                      seen_urls: set[str],
                      seen_titles: set[str]) -> list[dict]:
    new_articles, skipped = [], 0
    for a in articles:
        if a["url"] in seen_urls or _normalize_title(a["title"]) in seen_titles:
            skipped += 1
            continue
        new_articles.append(a)
    print(f"  중복 제외 {skipped}개 → 새 기사 {len(new_articles)}개")
    return new_articles


def prioritize_and_limit(articles: list[dict]) -> list[dict]:
    """주요 플랫폼 기사 우선 배치 후 MAX_TOTAL_ARTICLES로 제한."""
    priority, others = [], []
    for a in articles:
        if any(kw in a["title"] for kw in PRIORITY_KEYWORDS):
            priority.append(a)
        else:
            others.append(a)
    result = (priority + others)[:MAX_TOTAL_ARTICLES]
    print(f"  우선순위 정렬 후 {len(result)}개 선택 (주요 플랫폼 {len(priority)}개)")
    return result


# ── 뉴스 수집 ────────────────────────────────────────────────────────────────
def fetch_articles() -> list[dict]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    articles, seen_urls, skipped_old = [], set(), 0

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
                    "title":       entry.get("title", "(제목 없음)"),
                    "title_ko":    "",
                    "url":         url,
                    "source":      feed_info["label"],
                    "region":      feed_info["region"],
                    "subcategory": "기타",
                    "summary":     "",
                    "insight":     "",
                })
                count += 1
        except Exception as e:
            print(f"  [오류] {feed_info['label']} 피드 실패: {e}")

    print(f"  총 {len(articles)}개 기사 수집 (7일 초과 {skipped_old}개 제외)")
    return articles


# ── Claude 요약 + 분류 ────────────────────────────────────────────────────────
def summarize_articles(articles: list[dict]) -> list[dict]:
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY 없음")
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    titles_block = "\n".join(
        f"[{i+1}] ({a['region']} / {a['source']}) {a['title']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""당신은 이커머스/유통 업계 시니어 MD입니다.
아래 기사 목록의 각 기사에 대해 다음을 작성하세요.

작성 규칙:
- 제목: 원문 기사 제목을 자연스러운 한국어로 번역 (한국어 기사는 원제목 그대로)
- 소카테고리: 기사의 지역에 맞게 아래에서 하나 선택
  * 국내(🇰🇷) 기사 선택지: 주요 플랫폼 / 플랫폼 / 배송/물류 / 마케팅 / 유한킴벌리 경쟁사 / 기타
    - 주요 플랫폼: 쿠팡, 네이버, 컬리, 올리브영 관련 기사에만 사용
    - 유한킴벌리 경쟁사: 화장지, 생리대, 기저귀, 물티슈, 유아스킨케어 카테고리 관련
  * 글로벌(🌎) 기사 선택지: 플랫폼 / 배송/물류 / 마케팅 / 기타
- 요약: 핵심 내용을 '- '로 시작하는 불렛포인트 2~3개로 작성 (각 항목 한 줄 이내, 사실 중심, 간결하게)
- 시사점: 실무자가 참고할 1문장 (간결하게)
- 이모지, **, ### 등 특수기호 사용 금지
- 모든 출력은 한국어로 작성

형식 (반드시 준수):
[번호]
제목: (한국어 제목)
소카테고리: (소카테고리명)
요약:
- (핵심 1)
- (핵심 2)
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

    blocks = re.split(r"\[(\d+)\]", raw)
    for i in range(1, len(blocks), 2):
        idx = int(blocks[i]) - 1
        if idx < 0 or idx >= len(articles):
            continue
        text = blocks[i + 1].strip() if i + 1 < len(blocks) else ""

        title_m = re.search(r"제목:\s*(.+)", text)
        articles[idx]["title_ko"] = title_m.group(1).strip() if title_m else articles[idx]["title"]

        subcat_m = re.search(r"소카테고리:\s*(.+)", text)
        if subcat_m:
            articles[idx]["subcategory"] = subcat_m.group(1).strip()

        sum_m = re.search(r"요약:\s*([\s\S]+?)(?=\n시사점:|$)", text)
        if sum_m:
            articles[idx]["summary"] = sum_m.group(1).strip()
        else:
            fallback = re.sub(r"(제목|소카테고리|시사점):.+\n?", "", text).strip()
            articles[idx]["summary"] = fallback

        ins_m = re.search(r"시사점:\s*(.+)", text)
        if ins_m:
            articles[idx]["insight"] = ins_m.group(1).strip()

    return articles


# ── 핵심 트렌드 도출 ─────────────────────────────────────────────────────────
def generate_insights(articles: list[dict]) -> list[str]:
    if not CLAUDE_API_KEY:
        return []
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    titles_block = "\n".join(
        f"[{i+1}] ({a['region']} / {a['subcategory']}) {a['title']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""아래 커머스 뉴스 기사 목록을 보고, 오늘 이커머스/유통 업계 실무자가 꼭 알아야 할 핵심 트렌드 3가지를 작성하세요.

규칙:
- 각 트렌드는 1~2문장, 간결하게
- 여러 기사를 종합한 통찰 (단순 기사 요약 아님)
- 이모지, **, ### 등 특수기호 사용 금지
- 형식 반드시 준수

형식:
① (트렌드 1)
② (트렌드 2)
③ (트렌드 3)

기사 목록:
{titles_block}"""

    print("  [인사이트] 핵심 트렌드 도출 중...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    trends = re.findall(r"[①②③]\s*(.+)", raw)
    return [_strip_md(t) for t in trends[:3]] if trends else [_strip_md(raw)]


# ── 그룹화 헬퍼 ──────────────────────────────────────────────────────────────
def _group_articles(articles: list[dict]):
    grouped = defaultdict(lambda: defaultdict(list))
    for a in articles:
        grouped[a["region"]][a["subcategory"]].append(a)
    return grouped


# ── 파일 저장 ────────────────────────────────────────────────────────────────
def save_to_file(articles: list[dict], date_str: str, insights: list[str]) -> str:
    os.makedirs(TRENDS_DIR, exist_ok=True)
    filepath = os.path.join(TRENDS_DIR, f"trend_{date_str}.txt")

    lines = [
        f"커머스 뉴스 트렌드 | {date_str}",
        "---",
        "",
        "🔑 오늘의 핵심 트렌드",
        "",
    ]
    for trend in insights:
        lines.append(_strip_md(trend))
    lines.append("")

    grouped = _group_articles(articles)
    article_num = 1

    for region in REGIONS:
        if region not in grouped:
            continue
        lines += ["---", region, "---", ""]
        subcats = KR_SUBCATS if region == REGION_KR else GL_SUBCATS
        subcat_groups = grouped[region]
        ordered = [s for s in subcats if s in subcat_groups]
        extra   = [s for s in subcat_groups if s not in subcats]

        for subcat in ordered + extra:
            lines += [f"[ {subcat} ]", ""]
            for a in subcat_groups[subcat]:
                display_title = _strip_md(a.get("title_ko") or a["title"])
                lines += [f"{circle_num(article_num)} {display_title}",
                          f"   출처: {a['source']}", ""]
                for line in a["summary"].splitlines():
                    if line.strip():
                        lines.append(f"   {_strip_md(line.strip())}")
                if a.get("insight"):
                    lines += ["", f"   시사점: {_strip_md(a['insight'])}"]
                lines += ["", f"   원문: {a['url']}", "---", ""]
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
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _make_rich_text(text)}}

def _make_divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}

def _make_heading(text: str, level: int = 3) -> dict:
    h = f"heading_{level}"
    return {"object": "block", "type": h, h: {"rich_text": _make_rich_text(text)}}

def _make_callout(text: str, emoji: str = "💡") -> dict:
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": _make_rich_text(text),
                        "icon": {"type": "emoji", "emoji": emoji},
                        "color": "yellow_background"}}

def _make_bold_paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text",
                                          "text": {"content": text[:2000]},
                                          "annotations": {"bold": True}}]}}

def _make_link_paragraph(text: str, url: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text",
                                          "text": {"content": text, "link": {"url": url}}}]}}


# ── Notion 업로드 ────────────────────────────────────────────────────────────
def upload_to_notion(articles: list[dict], date_str: str, insights: list[str]):
    if not NOTION_API_KEY:
        print("  [건너뜀] NOTION_API_KEY 없음")
        return

    notion = Client(auth=NOTION_API_KEY)
    blocks: list[dict] = [
        _make_heading(f"커머스 뉴스 트렌드 — {date_str}", level=2),
        _make_divider(),
    ]

    if insights:
        blocks.append(_make_heading("🔑 오늘의 핵심 트렌드", level=2))
        for trend in insights:
            blocks.append(_make_callout(_strip_md(trend)))
        blocks.append(_make_divider())

    grouped = _group_articles(articles)
    article_num = 1

    for region in REGIONS:
        if region not in grouped:
            continue
        blocks.append(_make_heading(region, level=2))
        subcats = KR_SUBCATS if region == REGION_KR else GL_SUBCATS
        subcat_groups = grouped[region]
        ordered = [s for s in subcats if s in subcat_groups]
        extra   = [s for s in subcat_groups if s not in subcats]

        for subcat in ordered + extra:
            blocks.append(_make_heading(f"[ {subcat} ]", level=3))
            for a in subcat_groups[subcat]:
                display_title = _strip_md(a.get("title_ko") or a["title"])
                blocks.append(_make_bold_paragraph(f"{circle_num(article_num)} {display_title}"))
                blocks.append(_make_paragraph(f"출처: {a['source']}"))
                for line in a["summary"].splitlines():
                    if line.strip():
                        blocks.append(_make_paragraph(_strip_md(line.strip())))
                if a.get("insight"):
                    blocks.append(_make_paragraph(f"시사점: {_strip_md(a['insight'])}"))
                blocks.append(_make_link_paragraph("원문 보기", a["url"]))
                blocks.append(_make_divider())
                article_num += 1

    if NOTION_DATABASE_ID:
        print("  [Notion] Database에 새 페이지 생성 중...")
        chunk_size = 95
        page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={"Name": {"title": _make_rich_text(f"커머스 뉴스 트렌드 {date_str}")}},
            children=blocks[:chunk_size],
        )
        for start in range(chunk_size, len(blocks), chunk_size):
            notion.blocks.children.append(page["id"], children=blocks[start:start + chunk_size])
        print(f"  [Notion] 완료 → {page['url']}")
        return

    if NOTION_PAGE_ID:
        print("  [Notion] 기존 페이지에 블록 추가 중...")
        chunk_size = 95
        for start in range(0, len(blocks), chunk_size):
            notion.blocks.children.append(NOTION_PAGE_ID, children=blocks[start:start + chunk_size])
        print("  [Notion] 완료")
        return

    print("  [건너뜀] NOTION_DATABASE_ID 또는 NOTION_PAGE_ID를 설정하세요.")


# ── 이메일 HTML ──────────────────────────────────────────────────────────────
def _build_html(articles: list[dict], date_str: str, insights: list[str]) -> str:
    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    grouped = _group_articles(articles)

    trends_html = "".join(
        f"<p style='margin:4px 0;font-size:14px;color:#1a1a1a;'>{esc(_strip_md(t))}</p>"
        for t in insights
    )

    sections_html = ""
    article_num = 1

    for region in REGIONS:
        if region not in grouped:
            continue
        subcats = KR_SUBCATS if region == REGION_KR else GL_SUBCATS
        subcat_groups = grouped[region]
        ordered = [s for s in subcats if s in subcat_groups]
        extra   = [s for s in subcat_groups if s not in subcats]

        region_html = ""
        for subcat in ordered + extra:
            articles_html = ""
            for a in subcat_groups[subcat]:
                display_title = esc(_strip_md(a.get("title_ko") or a["title"]))
                bullets = []
                for line in a["summary"].splitlines():
                    line = line.strip()
                    if line:
                        content = line[2:] if line.startswith("- ") else line
                        bullets.append(f"<li style='margin:3px 0;'>{esc(_strip_md(content))}</li>")
                bullets_html = "".join(bullets)
                insight_html = (
                    f"<p style='margin:6px 0 0;font-size:13px;color:#374151;'>"
                    f"시사점: {esc(_strip_md(a['insight']))}</p>"
                    if a.get("insight") else ""
                )
                articles_html += f"""
                <div style='margin-bottom:20px;padding-bottom:20px;border-bottom:1px solid #f3f4f6;'>
                  <p style='margin:0 0 2px;font-size:14px;font-weight:600;color:#111827;'>
                    {circle_num(article_num)} {display_title}
                  </p>
                  <p style='margin:0 0 8px;font-size:11px;color:#9ca3af;'>출처: {esc(a['source'])}</p>
                  <ul style='margin:0;padding-left:16px;font-size:13px;color:#374151;line-height:1.6;'>
                    {bullets_html}
                  </ul>
                  {insight_html}
                  <p style='margin:8px 0 0;'>
                    <a href='{a["url"]}' style='font-size:12px;color:#6b7280;'>원문 보기</a>
                  </p>
                </div>"""
                article_num += 1

            region_html += f"""
            <h3 style='margin:18px 0 10px;font-size:12px;font-weight:600;color:#6b7280;
                       text-transform:uppercase;letter-spacing:.06em;
                       border-bottom:1px solid #f3f4f6;padding-bottom:5px;'>
              {esc(subcat)}
            </h3>
            {articles_html}"""

        sections_html += f"""
        <div>
          <h2 style='margin:28px 0 14px;font-size:16px;font-weight:700;color:#111827;'>
            {esc(region)}
          </h2>
          {region_html}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"></head>
<body style='margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'>
  <div style='max-width:640px;margin:32px auto;background:#fff;
              border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden;'>
    <div style='background:#111827;padding:26px 32px;'>
      <p style='margin:0;font-size:11px;color:#9ca3af;letter-spacing:.08em;'>DAILY BRIEFING</p>
      <h1 style='margin:4px 0 0;font-size:20px;font-weight:700;color:#fff;'>커머스 뉴스 트렌드</h1>
      <p style='margin:5px 0 0;font-size:12px;color:#9ca3af;'>{date_str}</p>
    </div>
    <div style='padding:26px 32px;'>
      <div style='background:#fefce8;border-left:4px solid #eab308;
                  border-radius:4px;padding:14px 18px;margin-bottom:24px;'>
        <p style='margin:0 0 8px;font-size:12px;font-weight:700;color:#854d0e;'>
          🔑 오늘의 핵심 트렌드
        </p>
        {trends_html}
      </div>
      {sections_html}
    </div>
    <div style='background:#f9fafb;padding:14px 32px;text-align:center;
                border-top:1px solid #e5e7eb;'>
      <p style='margin:0;font-size:11px;color:#9ca3af;'>
        자동 생성 · {date_str} · 커머스 뉴스 아카이버
      </p>
    </div>
  </div>
</body></html>"""


# ── 이메일 발송 ──────────────────────────────────────────────────────────────
def send_email(articles: list[dict], date_str: str, insights: list[str]):
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
        "subject": f"[커머스 뉴스] {date_str}",
        "html":    html,
    }
    result = resend.Emails.send(params)
    print(f"  [이메일] 완료 → id: {result.get('id', '-')}")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    date_str = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    mode_tag = "  [미리보기 모드]" if PREVIEW else ""
    print(f"\n▶ 커머스 뉴스 아카이빙 시작 [{date_str}]{mode_tag}\n")

    print("1/7  뉴스 수집")
    articles = fetch_articles()
    if not articles:
        print("수집된 기사가 없습니다. 종료합니다.")
        sys.exit(1)

    print("\n2/7  중복 필터링 (최근 7일 리포트 비교)")
    seen_urls, seen_titles = load_seen_records(days=7)
    articles = filter_duplicates(articles, seen_urls, seen_titles)

    if len(articles) < MIN_NEW_ARTICLES:
        print(f"\n발송 조건 미달 (새 뉴스 {len(articles)}개) — 종료합니다.")
        sys.exit(0)

    print("\n3/7  우선순위 정렬 및 최대 20개 제한")
    articles = prioritize_and_limit(articles)

    print("\n4/7  Claude 요약 + 소카테고리 분류")
    articles = summarize_articles(articles)

    print("\n5/7  핵심 트렌드 도출")
    insights = generate_insights(articles)

    print("\n6/7  파일 저장")
    filepath = save_to_file(articles, date_str, insights)

    if PREVIEW:
        print("\n[미리보기 모드] Notion 업로드 및 이메일 발송 건너뜀.")
    else:
        print("\n7/7  Notion 업로드 + 이메일 발송")
        upload_to_notion(articles, date_str, insights)
        send_email(articles, date_str, insights)

    print(f"\n✓ 완료! → {filepath}\n")


if __name__ == "__main__":
    main()
