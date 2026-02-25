"""
이커머스/FMCG 뉴스 아카이버
- 한국 + 영문 뉴스 RSS 수집
- Claude API로 3줄 요약
- ~/trends/trend_YYYY-MM-DD.txt 저장
- Notion 페이지 업로드
"""

import os
import sys
import datetime
sys.stdout.reconfigure(encoding="utf-8")
import textwrap
import feedparser
import anthropic
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ────────────────────────────────────────────────────────────────────
CLAUDE_API_KEY    = os.getenv("CLAUDE_API_KEY")
NOTION_API_KEY    = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")   # DB 방식
NOTION_PAGE_ID    = os.getenv("NOTION_PAGE_ID")        # 단일 페이지 방식 (DB 없을 때)

TRENDS_DIR = os.getenv("TRENDS_DIR", r"C:\Users\USER\Desktop\뉴스아카이빙\trends")
MAX_ARTICLES_PER_FEED = 5   # 피드 당 최대 기사 수

# ── RSS 피드 목록 ─────────────────────────────────────────────────────────
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
    # ── 영문 (Google News 검색 RSS) ───────────────────────────────────────
    {
        "label": "EN-eCommerce",
        "url": "https://news.google.com/rss/search?q=ecommerce+retail+trend&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "label": "EN-FMCG",
        "url": "https://news.google.com/rss/search?q=FMCG+consumer+goods+trend&hl=en-US&gl=US&ceid=US:en",
    },
]


# ── 뉴스 수집 ────────────────────────────────────────────────────────────────
def fetch_articles() -> list[dict]:
    """RSS 피드에서 기사 수집. 중복 URL 제거 + 7일 이내 기사만 필터링."""
    import time as _time
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

                # 발행일 파싱 — published_parsed 없으면 통과 허용
                published = entry.get("published_parsed")
                if published:
                    pub_dt = datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc)
                    if pub_dt < cutoff:
                        skipped_old += 1
                        continue

                seen_urls.add(url)
                articles.append({
                    "title":  entry.get("title", "(제목 없음)"),
                    "url":    url,
                    "source": feed_info["label"],
                    "summary": "",   # Claude가 채울 필드
                })
                count += 1
        except Exception as e:
            print(f"  [오류] {feed_info['label']} 피드 실패: {e}")

    print(f"  총 {len(articles)}개 기사 수집 (7일 초과 {skipped_old}개 제외)")
    return articles


# ── Claude 요약 ──────────────────────────────────────────────────────────────
def summarize_articles(articles: list[dict]) -> list[dict]:
    """Claude Haiku로 각 기사 제목 기반 3줄 요약 생성."""
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY 환경변수가 없습니다.")

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    # 한 번에 배치 요약 (비용/속도 최적화)
    titles_block = "\n".join(
        f"[{i+1}] ({a['source']}) {a['title']}" for i, a in enumerate(articles)
    )

    prompt = f"""당신은 이커머스/FMCG 업계 현장을 잘 아는 시니어 MD 출신 블로거입니다.
아래 뉴스 기사 제목들을 읽고, 실무자(MD, 마케터, 사업기획자)에게 실질적으로 도움이 되는
현장감 있는 3문장 요약을 작성하세요.

작성 규칙:
- 딱딱한 bullet point 금지. 자연스럽게 이어지는 3문장 산문체
- 어투는 블로그 스타일 (예: "~입니다", "~에요", "~될 것 같습니다")
- 단순 사실 나열 말고, 업계에 미치는 영향과 실무적 시사점 중심
- 영문 기사도 한국어로 작성
- 각 요약은 정확히 3문장

예시 (좋은 요약):
대형마트 새벽배송 규제가 풀리면서 이커머스 판이 다시 흔들릴 것 같습니다.
쿠팡·마켓컬리 입장에서는 대형마트가 새벽배송에 본격 뛰어들면 차별화 전략을 다시 짜야 할 상황이에요.
특히 신선식품 카테고리는 직접적인 타격이 예상됩니다.

형식 (반드시 준수):
[번호]
(3문장 산문 요약)

기사 목록:
{titles_block}

각 [번호] 블록을 순서대로 작성하세요."""

    print("  [요약] Claude API 호출 중...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text

    # 파싱: [1] ~ [N] 블록 분리
    import re
    blocks = re.split(r"\[(\d+)\]", raw)
    summary_map: dict[int, str] = {}
    for i in range(1, len(blocks), 2):
        idx = int(blocks[i])
        text = blocks[i + 1].strip() if i + 1 < len(blocks) else ""
        summary_map[idx] = text

    for i, article in enumerate(articles):
        article["summary"] = summary_map.get(i + 1, "요약 생성 실패")

    return articles


# ── 파일 저장 ────────────────────────────────────────────────────────────────
def save_to_file(articles: list[dict], date_str: str) -> str:
    """~/trends/trend_YYYY-MM-DD.txt 에 저장."""
    os.makedirs(TRENDS_DIR, exist_ok=True)
    filepath = os.path.join(TRENDS_DIR, f"trend_{date_str}.txt")

    lines = [
        f"═══════════════════════════════════════════════════",
        f"  이커머스/FMCG 뉴스 트렌드 | {date_str}",
        f"═══════════════════════════════════════════════════",
        "",
    ]

    for i, a in enumerate(articles, 1):
        lines += [
            f"[{i}] {a['title']}",
            f"    출처: {a['source']}",
            "",
        ]
        for bullet in a["summary"].splitlines():
            if bullet.strip():
                lines.append(f"    {bullet.strip()}")
        lines += [
            "",
            f"    URL: {a['url']}",
            "─" * 51,
            "",
        ]

    lines.append(f"생성: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  [저장] {filepath}")
    return filepath


# ── Notion 업로드 ────────────────────────────────────────────────────────────
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


def upload_to_notion(articles: list[dict], date_str: str):
    """Notion에 날짜별 페이지 생성 또는 Database 행 추가."""
    if not NOTION_API_KEY:
        print("  [건너뜀] NOTION_API_KEY 없음")
        return

    notion = Client(auth=NOTION_API_KEY)

    # ── 본문 블록 구성 ──────────────────────────────────────────────────
    blocks: list[dict] = [
        _make_heading(f"이커머스/FMCG 뉴스 트렌드 — {date_str}", level=2),
        _make_divider(),
    ]

    for i, a in enumerate(articles, 1):
        blocks.append(_make_heading(f"[{i}] {a['title']}", level=3))
        blocks.append(_make_paragraph(f"출처 카테고리: {a['source']}"))
        for bullet in a["summary"].splitlines():
            if bullet.strip():
                blocks.append(_make_paragraph(bullet.strip()))
        blocks.append(_make_paragraph(f"🔗 {a['url']}"))
        blocks.append(_make_divider())

    # ── Database 방식 (NOTION_DATABASE_ID 있을 때) ──────────────────────
    if NOTION_DATABASE_ID:
        print("  [Notion] Database에 새 페이지 생성 중...")
        chunk_size = 95
        # 첫 청크를 포함해 페이지 생성 (Notion API: children 최대 100개)
        page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "Name": {
                    "title": _make_rich_text(f"트렌드 리포트 {date_str}")
                },
            },
            children=blocks[:chunk_size],
        )
        # 나머지 블록을 청크로 추가
        for start in range(chunk_size, len(blocks), chunk_size):
            notion.blocks.children.append(
                page["id"],
                children=blocks[start: start + chunk_size],
            )
        print(f"  [Notion] 완료 → {page['url']}")
        return

    # ── 단일 페이지 방식 (NOTION_PAGE_ID 있을 때) ──────────────────────
    if NOTION_PAGE_ID:
        print("  [Notion] 기존 페이지에 블록 추가 중...")
        # 청크 단위로 전송 (Notion API: 한 번에 100 블록 제한)
        chunk_size = 95
        for start in range(0, len(blocks), chunk_size):
            notion.blocks.children.append(
                NOTION_PAGE_ID,
                children=blocks[start: start + chunk_size],
            )
        print("  [Notion] 완료")
        return

    print("  [건너뜀] NOTION_DATABASE_ID 또는 NOTION_PAGE_ID를 설정하세요.")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"\n▶ 뉴스 아카이빙 시작 [{date_str}]\n")

    print("1/4  뉴스 수집")
    articles = fetch_articles()
    if not articles:
        print("수집된 기사가 없습니다. 종료합니다.")
        sys.exit(1)

    print("\n2/4  Claude 요약")
    articles = summarize_articles(articles)

    print("\n3/4  파일 저장")
    filepath = save_to_file(articles, date_str)

    print("\n4/4  Notion 업로드")
    upload_to_notion(articles, date_str)

    print(f"\n✓ 완료! → {filepath}\n")


if __name__ == "__main__":
    main()
