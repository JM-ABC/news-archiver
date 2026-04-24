"""
커머스 뉴스 아카이버 v3
- 대카테고리: 🇰🇷 국내 뉴스 / 🌎 글로벌 뉴스
- 소카테고리: 플랫폼 / 배송·물류 / 마케팅 / 유한킴벌리 경쟁사 / 기타
- RSS 12개 소스, 최대 20개 기사 (플랫폼 우선)
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
EMAIL_BCC          = os.getenv("EMAIL_BCC", "")
TRENDS_DIR         = os.getenv("TRENDS_DIR", "./trends")

MAX_ARTICLES_PER_FEED = 10
MIN_NEW_ARTICLES      = 10
MAX_TOTAL_ARTICLES    = 20
PREVIEW               = "--preview" in sys.argv

# 국내 우선순위 키워드 (필수 체크 브랜드)
KR_PRIORITY_KEYWORDS = [
    "쿠팡", "네이버쇼핑", "네이버", "컬리", "마켓컬리",
    "G마켓", "11번가", "무신사", "올리브영",
    "이마트", "홈플러스", "롯데마트", "코스트코",
]

# 글로벌 우선순위 키워드 (필수 체크 브랜드)
GL_PRIORITY_KEYWORDS = [
    "Amazon", "Walmart", "Target", "Costco", "eBay",
    "Temu", "Shein", "TikTok Shop", "AliExpress",
    "Zara", "Inditex", "Nike", "Adidas",
    "Kroger", "Instacart", "Shopee", "JD.com", "Mercado Libre",
]

PRIORITY_KEYWORDS = KR_PRIORITY_KEYWORDS + GL_PRIORITY_KEYWORDS

# 대카테고리
REGION_KR = "🇰🇷 국내 뉴스"
REGION_GL = "🌎 글로벌 뉴스"
REGIONS   = [REGION_KR, REGION_GL]

# 소카테고리 (출력 순서)
KR_SUBCATS = ["플랫폼", "배송/물류", "마케팅", "유한킴벌리 경쟁사", "기타"]
GL_SUBCATS = ["플랫폼", "배송/물류", "마케팅", "기타"]

# ── RSS 피드 ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # 국내 — 브랜드별 개별 수집 (각 최대 3개, 누락 방지)
    {"label": "KR-쿠팡",       "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=쿠팡&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-네이버쇼핑", "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=네이버쇼핑+스마트스토어&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-컬리",       "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=컬리+마켓컬리&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-무신사",     "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=무신사&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-올리브영",   "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=올리브영&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-이마트",     "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=이마트&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-홈플러스",   "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=홈플러스&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-롯데마트",   "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=롯데마트&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-11번가",     "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=11번가&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-G마켓",      "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=G마켓&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-다이소",     "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=다이소&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-카카오쇼핑", "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=카카오쇼핑+카카오커머스&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-티몬",       "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=티몬&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-위메프",     "region": REGION_KR, "max": 3,
     "url": "https://news.google.com/rss/search?q=위메프&hl=ko&gl=KR&ceid=KR:ko"},
    # 국내 — 이커머스 전반·AI·라이브커머스
    {"label": "KR-이커머스",   "region": REGION_KR,
     "url": "https://news.google.com/rss/search?q=이커머스+라이브커머스+AI커머스+온라인유통+물류혁신&hl=ko&gl=KR&ceid=KR:ko"},
    # 국내 — 유한킴벌리 경쟁사
    {"label": "KR-유한킴벌리", "region": REGION_KR,
     "url": "https://news.google.com/rss/search?q=화장지+생리대+기저귀+물티슈+유아스킨케어+유한킴벌리+깨끗한나라&hl=ko&gl=KR&ceid=KR:ko"},
    # 국내 — 주제별 보강 (쿼터 확보)
    {"label": "KR-물류택배",   "region": REGION_KR, "max": 5,
     "url": "https://news.google.com/rss/search?q=택배+풀필먼트+새벽배송+당일배송+물류센터&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-소비트렌드", "region": REGION_KR, "max": 5,
     "url": "https://news.google.com/rss/search?q=소비트렌드+소비자행동+온라인소비+MZ소비+알뜰소비&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-유통정책",   "region": REGION_KR, "max": 4,
     "url": "https://news.google.com/rss/search?q=유통규제+전자상거래법+공정거래+온라인플랫폼규제&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-패션뷰티",   "region": REGION_KR, "max": 4,
     "url": "https://news.google.com/rss/search?q=패션플랫폼+뷰티플랫폼+온라인패션+K뷰티+뷰티이커머스&hl=ko&gl=KR&ceid=KR:ko"},
    # 국내 — 버티컬 플랫폼 (파급력 있는 뉴스만 수집, 각 최대 2개)
    {"label": "KR-배민",       "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=배달의민족+배민&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-29CM",       "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=29CM+에이블리+스타일쉐어&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-당근",       "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=당근마켓+당근페이&hl=ko&gl=KR&ceid=KR:ko"},
    # 국내 — 자사몰·백화점·버티컬 (후순위, 각 최대 2개)
    {"label": "KR-SSG",        "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=SSG닷컴+신세계닷컴&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-롯데온",     "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=롯데온+롯데이커머스&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-더현대",     "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=더현대+현대백화점+온라인&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-CJ온스타일", "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=CJ온스타일+CJ더마켓&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-GS리테일",   "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=GS샵+GS리테일+GS더프레시&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-오늘의집",   "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=오늘의집&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-지그재그",   "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=지그재그+카카오스타일&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-아모레",     "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=아모레퍼시픽+이니스프리+설화수+온라인몰&hl=ko&gl=KR&ceid=KR:ko"},
    {"label": "KR-LGH&H",      "region": REGION_KR, "max": 2,
     "url": "https://news.google.com/rss/search?q=LG생활건강+더페이스샵+온라인커머스&hl=ko&gl=KR&ceid=KR:ko"},
    # 글로벌 — 메가 유통사 (Amazon·Walmart·Target·Costco·eBay)
    {"label": "GL-메가유통",   "region": REGION_GL,
     "url": "https://news.google.com/rss/search?q=Amazon+Walmart+Target+Costco+eBay+retail&hl=en-US&gl=US&ceid=US:en"},
    # 글로벌 — 신흥 플랫폼·패스트패션 (Temu·Shein·TikTok Shop·AliExpress·Zara·Nike)
    {"label": "GL-뉴커머스",   "region": REGION_GL,
     "url": "https://news.google.com/rss/search?q=Temu+Shein+TikTok+Shop+AliExpress+Zara+Nike+Adidas+ecommerce&hl=en-US&gl=US&ceid=US:en"},
    # 글로벌 전문 미디어
    {"label": "EN-RetailDive",    "region": REGION_GL, "url": "https://www.retaildive.com/feeds/news/"},
    {"label": "EN-ModernRetail",  "region": REGION_GL, "url": "https://www.modernretail.co/feed/"},
    {"label": "EN-GroceryDive",   "region": REGION_GL, "url": "https://www.grocerydive.com/feeds/news/"},
    {"label": "EN-PYMNTS",        "region": REGION_GL, "url": "https://www.pymnts.com/category/retail/feed/"},
    {"label": "EN-ChainStoreAge", "region": REGION_GL, "url": "https://chainstoreage.com/feed"},
    # 아시아 — Shopee·JD.com·Mercado Libre 포함
    {"label": "ASIA-Retail",      "region": REGION_GL,
     "url": "https://news.google.com/rss/search?q=Shopee+JD.com+Mercado+Libre+Kroger+Instacart+Asia+ecommerce&hl=en-US&gl=US&ceid=US:en"},
    # 글로벌 — 버티컬·신흥 플랫폼 (후순위, 각 최대 2개)
    {"label": "GL-Shopify",       "region": REGION_GL, "max": 2,
     "url": "https://news.google.com/rss/search?q=Shopify+D2C+direct-to-consumer+ecommerce&hl=en-US&gl=US&ceid=US:en"},
    {"label": "GL-유럽패션",      "region": REGION_GL, "max": 2,
     "url": "https://news.google.com/rss/search?q=Zalando+ASOS+ecommerce&hl=en-US&gl=US&ceid=US:en"},
    {"label": "GL-Flipkart",      "region": REGION_GL, "max": 2,
     "url": "https://news.google.com/rss/search?q=Flipkart+India+ecommerce&hl=en-US&gl=US&ceid=US:en"},
    {"label": "GL-버티컬",        "region": REGION_GL, "max": 2,
     "url": "https://news.google.com/rss/search?q=Etsy+Wayfair+Chewy+ecommerce&hl=en-US&gl=US&ceid=US:en"},
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
    front = re.split(r"[…:\-]", title)[0]
    return re.sub(r"[^\w가-힣]", "", front.lower())

def _title_bigrams(title: str) -> set[str]:
    norm = _normalize_title(title)
    return {norm[i:i+2] for i in range(len(norm) - 1)} if len(norm) > 1 else set()

def deduplicate_within_session(articles: list[dict]) -> list[dict]:
    """동일 사건 다중 보도 제거 — 제목 바이그램 유사도 60% 이상이면 중복으로 처리."""
    kept_bigrams: list[set[str]] = []
    result: list[dict] = []
    skipped = 0
    for a in articles:
        bg = _title_bigrams(a["title"])
        is_dup = any(
            bg and kb and len(bg & kb) / min(len(bg), len(kb)) >= 0.50
            for kb in kept_bigrams
        )
        if is_dup:
            skipped += 1
        else:
            kept_bigrams.append(bg)
            result.append(a)
    if skipped:
        print(f"  동일 사건 중복 {skipped}개 제거 → {len(result)}개 유지")
    return result


# ── 인사 기사 필터링 ──────────────────────────────────────────────────────────
# 단순 임원 교체·발령 패턴 — 제목만으로 명확히 판별되는 경우만 제외
_HR_PATTERNS = [
    # 국내: "~로 선임", "~에 선임", "대표이사 취임" 등
    r"(대표이사|사장|부사장|전무|상무|이사|본부장|센터장).{0,6}(선임|임명|취임|발령|부임)",
    r"(선임|임명|취임|발령).{0,6}(대표이사|사장|부사장|전무|상무|이사|본부장)",
    r"임원\s*인사",
    r"인사\s*발령",
    r"인사\s*이동",
    # 영문: "appointed as", "names new CEO", "steps down as", "resigns as"
    r"\bappointed\s+(as\s+)?(new\s+)?(CEO|COO|CFO|CTO|CMO|President|Chief|VP|Director)\b",
    r"\bnames\s+(new\s+)?(CEO|COO|CFO|CTO|CMO|President|Chief|VP|Director)\b",
    r"\b(steps?\s+down|resign(s|ed)?)\s+as\s+(CEO|COO|CFO|CTO|CMO|President|Chief)\b",
]
_HR_RE = re.compile("|".join(_HR_PATTERNS), re.IGNORECASE)

def filter_hr_articles(articles: list[dict]) -> list[dict]:
    """단순 인사 발령·임원 교체 기사를 제목 패턴으로 사전 제거."""
    kept, skipped = [], 0
    for a in articles:
        if _HR_RE.search(a["title"]):
            skipped += 1
        else:
            kept.append(a)
    if skipped:
        print(f"  인사 기사 {skipped}개 제거 → {len(kept)}개 유지")
    return kept


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


KR_MAX       = 13  # 국내 최대 기사 수
GL_MAX       =  7  # 글로벌 최대 기사 수 (최소 보장)
PER_BRAND_MAX = 2  # 브랜드(우선순위 키워드)별 최대 기사 수 — 상위 플랫폼 과점 방지

def _brand_match(kw: str, title: str, source: str) -> bool:
    """1순위: 소스 라벨 포함 여부. 2순위: 제목 앞 20자 + 주격 조사(이/가/은/는/,) 패턴."""
    if kw in source:
        return True
    front = title[:20]
    return bool(re.search(re.escape(kw) + r"[이가은는,]", front))


def prioritize_and_limit(articles: list[dict]) -> list[dict]:
    """국내/글로벌 쿼터를 분리, 브랜드별 PER_BRAND_MAX개 상한 후 남은 슬롯은 비우선 기사로 채움.

    순서: [우선순위 기사(브랜드별 최대 2개)] + [비우선 기사]
    → overflow(상한 초과 브랜드 기사)는 결과에서 완전히 제외.
      단일 브랜드 과점을 방지하며, 빈 슬롯은 채우지 않고 그대로 둔다.
    """
    def _pick(pool: list[dict], limit: int, priority_kws: list[str]) -> list[dict]:
        brand_count: dict[str, int] = defaultdict(int)
        top, others, overflow = [], [], []
        capped: set[str] = set()

        for a in pool:
            # 1순위: 소스 라벨 매칭 / 2순위: 제목 앞 20자 + 주격 조사 패턴
            matched = next(
                (kw for kw in priority_kws if _brand_match(kw, a["title"], a["source"])),
                None,
            )
            if matched:
                if brand_count[matched] < PER_BRAND_MAX:
                    top.append(a)
                    brand_count[matched] += 1
                else:
                    capped.add(matched)
                    overflow.append(a)
            else:
                others.append(a)

        if capped:
            print(f"  브랜드 상한({PER_BRAND_MAX}개) 적용: {', '.join(sorted(capped))}")
        return (top + others)[:limit]

    kr = _pick([a for a in articles if a["region"] == REGION_KR], KR_MAX, KR_PRIORITY_KEYWORDS)
    gl = _pick([a for a in articles if a["region"] == REGION_GL], GL_MAX, GL_PRIORITY_KEYWORDS)
    result = kr + gl
    print(f"  국내 {len(kr)}개 + 글로벌 {len(gl)}개 = {len(result)}개 선택")
    return result


# ── 뉴스 수집 ────────────────────────────────────────────────────────────────
def fetch_articles() -> list[dict]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=4)
    articles, seen_urls, skipped_old = [], set(), 0

    for feed_info in RSS_FEEDS:
        print(f"  [수집] {feed_info['label']} ...")
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0
            for entry in feed.entries:
                if count >= feed_info.get("max", MAX_ARTICLES_PER_FEED):
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

    print(f"  총 {len(articles)}개 기사 수집 (4일 초과 {skipped_old}개 제외)")
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

    prompt = f"""당신은 이커머스/유통 업계 전문 분석가입니다. '커머스의 모든 것'을 다루는 브런치 칼럼니스트처럼 깊이 있는 시각으로 작성하세요.
아래 기사 목록의 각 기사에 대해 다음을 작성하세요.

[포함 기준 — 이런 기사를 우선 다루세요]
국내: 쿠팡·네이버쇼핑·컬리·G마켓·11번가·무신사·올리브영·이마트·홈플러스·롯데마트·코스트코 관련 (우선순위),
      배달의민족·29CM·당근마켓 등 버티컬 플랫폼은 시장 판도 변화·대형 투자·규제 이슈 등 파급력 있는 뉴스만 선별,
      이커머스 전략/실적/투자, AI커머스, 라이브커머스, 패션/뷰티 플랫폼, 물류/배송 혁신, 브랜드 유통 전략
글로벌: Amazon·Walmart·Target·Costco·eBay·Temu·Shein·TikTok Shop·AliExpress·Zara·Nike·Adidas·
        Kroger·Instacart·Shopee·JD.com·Mercado Libre 관련,
        대형 유통사 전략/실적, AI커머스 혁신, 글로벌 물류/공급망, D2C 브랜드 성장, 커머스에 영향 큰 관세/규제

[제외 기준 — 아래는 소카테고리 "기타"로 분류하거나 최소화]
- 단순 인사 발령·임원 교체 뉴스
- 주가·재무 단순 수치만 나열하는 보도
- 커머스/유통과 무관한 일반 사회/정치 뉴스

[소카테고리 분류]
* 국내(🇰🇷): 플랫폼 / 배송/물류 / 마케팅 / 유한킴벌리 경쟁사 / 기타
  - 플랫폼: 쿠팡·네이버·컬리·G마켓·11번가·무신사·올리브영·이마트·홈플러스·롯데마트·코스트코
  - 유한킴벌리 경쟁사: 화장지·생리대·기저귀·물티슈·유아스킨케어 카테고리
* 글로벌(🌎): 플랫폼 / 배송/물류 / 마케팅 / 기타

[요약 스타일 — 중요]
사실 중심으로 간결하게 2~3문장. 모든 문장은 "~합니다", "~입니다", "~전망됩니다" 등 격식체(합쇼체)로 끝낼 것.
숫자가 있으면 구체적으로 명시 (예: MAU 109만 명 감소, 점유율 7%p 하락).
단순 사실 나열이 아닌, 업계 맥락과 의미를 담은 전문 분석가 시각으로 작성할 것.

목표 톤 예시 (이 수준을 맞춰줘):
"대형마트 새벽배송 규제가 풀리면서 쿠팡 중심의 시장 구도가 흔들릴 가능성이 커지고 있습니다."
"홈플러스 폐점이 이어지면서 해당 상권의 유통 공백이 빠르게 확대되는 양상입니다."

절대 금지 표현:
- "~어요", "~거든요", "~겠어요", "~잖아요" — 캐주얼체 전면 금지
- "~할 것으로 보인다", "~예상된다", "~가 필요하다" — 보고서 말투

[시사점 스타일 — 중요]
전문 분석가 관점의 비즈니스 파장 분석 1~2문장. "왜 이게 중요한가"와 "어떤 기업·채널·전략에 어떤 영향을 미치는가"를 구체적으로 서술.
수치·경쟁사명·채널명 등 실제 맥락을 활용해 실무적 파장을 설명할 것.

목표 톤 예시:
"이 움직임은 올리브영 중심의 오프라인 뷰티 유통 구조에 온라인 플랫폼 경쟁을 추가하며 채널 다변화를 가속합니다."
"홈플러스 폐점이 가속화되면서 해당 상권 내 입점 브랜드의 오프라인 접점이 줄어드는 만큼, 대형마트 의존도가 높은 카테고리일수록 쿠팡·이마트몰로의 채널 재편 압박이 커집니다."

절대 금지 표현 (이것으로 시사점 끝내기 금지):
"~가 필요한 시점입니다", "~에 주목할 필요가 있습니다", "~을 검토할 시점입니다",
"~해야 합니다", "~해봐야 할 포인트예요", "~어요"

[공통 규칙]
- 제목: 한국어 기사는 원제목 그대로. 영문 기사는 아래 규칙으로 번역.
  [글로벌 기사 제목 번역 규칙]
  1. 직역이 아닌 한국 산업 뉴스 스타일로 번역합니다.
  2. 핵심 행동(확대, 인하, 폐점, 투자 등)을 중심으로 번역합니다.
  3. 불필요한 수식어는 제거합니다.
  4. 기업명은 그대로 유지합니다. (Amazon, Walmart, Target 등)
  5. 숫자나 규모는 반드시 유지합니다.
  예시: "Target reduces prices on 3K products" → "Target, 3,000개 상품 가격 인하로 고객 유치 전략 강화"
- 이모지, **, ### 등 특수기호 사용 금지
- 모든 출력은 한국어로 작성

형식 (반드시 준수):
[번호]
제목: (한국어 제목)
소카테고리: (소카테고리명)
요약:
- (핵심 1)
- (핵심 2)
👉 (액션 힌트 포함 1~2문장)

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

        sum_m = re.search(r"요약:\s*([\s\S]+?)(?=\n👉|\n시사점:|$)", text)
        if sum_m:
            articles[idx]["summary"] = sum_m.group(1).strip()
        else:
            fallback = re.sub(r"(제목|소카테고리|시사점):.+\n?|👉.+\n?", "", text).strip()
            articles[idx]["summary"] = fallback

        ins_m = re.search(r"(?:시사점:|👉)\s*([\s\S]+?)(?=\n\[|\Z)", text)
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

    prompt = f"""[역할]
당신은 이커머스·리테일 산업을 분석하는 시장 애널리스트입니다.
뉴스를 단순 요약하지 않고 "산업 구조 변화" 관점에서 핵심 트렌드를 도출합니다.

[목표]
여러 뉴스 기사들을 분석해
"오늘의 핵심 트렌드"를 3~5개 도출합니다.

각 트렌드는 여러 뉴스에서 공통적으로 나타나는
산업 변화 또는 전략 방향을 의미합니다.

[작성 규칙]

1. 기사 내용을 나열하지 말고 산업 변화 중심으로 정리합니다.
2. 하나의 트렌드는 2~3문장으로 작성합니다.
3. 첫 문장은 "시장 구조 변화"를 설명합니다.
4. 두 번째 문장은 그 변화의 산업적 의미를 설명합니다.
5. 필요하면 세 번째 문장에서 경쟁 구도 또는 확산 가능성을 설명합니다.
6. 기사 하나만으로 트렌드를 과장해 일반화하지 않습니다.
7. 불필요한 배경 설명은 제거합니다.
8. 트렌드를 작성하기 전, 해당 트렌드를 뒷받침하는 기사를 2개 이상 확인하세요. 뒷받침 기사가 1개뿐이라면 독립 트렌드로 만들지 마세요.
9. 여러 기사에서 공통적으로 나타나는 변화만 트렌드로 정리합니다.
10. 트렌드 제목 끝에 (근거: [기사번호, 기사번호]) 형식으로 근거 기사 번호를 반드시 표시하세요.

[문장 스타일]

- 모든 문장은 "~합니다 / ~입니다 / ~확대되고 있습니다 / ~나타나고 있습니다" 형태로 끝냅니다.
- "~보인다 / 예상된다 / 필요하다" 사용 금지
- 기사 재서술 금지
- 산업 구조 변화 중심 작성

[좋은 예시]

▶ 패션·이커머스 플랫폼의 뷰티 카테고리 진입이 본격화되고 있습니다.

무신사와 컬리가 뷰티 PB와 직매입 모델을 확대하면서 올리브영 중심의 오프라인 뷰티 유통 구조에 온라인 플랫폼 경쟁이 추가되고 있습니다.
플랫폼이 단순 중개를 넘어 상품 기획과 유통까지 통합하는 구조로 전환되며 뷰티 채널 다변화가 가속화되고 있습니다.

▶ 이커머스 물류 비용 구조 재조정 압력이 커지고 있습니다.

쿠팡과 배송 파트너사 간 단가 협상이 재개되면서 유가·인건비 상승에 따른 배송 단가 인상 요구와 플랫폼의 원가 절감 전략이 충돌하고 있습니다.
빠른 배송 경쟁이 심화된 가운데 물류 비용 구조의 지속 가능성에 대한 업계 재조정 움직임이 확대되는 양상입니다.

[형식] (반드시 준수)

▶ 트렌드 제목 (첫 문장이 곧 제목 — 산업 변화를 한 문장으로)

내용 2~3문장

▶ 트렌드 제목

내용 2~3문장

기사 목록:
{titles_block}"""

    print("  [인사이트] 핵심 트렌드 도출 중...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # 🔑 헤더 제거 후 ▶ 블록 파싱 (제목 + 내용 다중행)
    raw_clean = re.sub(r"🔑[^\n]*\n+", "", raw).strip()
    trends = re.findall(r"(▶\s*.+?)(?=\n\s*▶|\Z)", raw_clean, re.DOTALL)
    trends = [t.strip() for t in trends if t.strip()]
    # 근거 태그 및 trailing --- 제거 (근거:, 근bzw: 등 변형 포함)
    cleaned = [re.sub(r"\s*\(근[^)]*\)", "", t).strip() for t in trends[:5]]
    cleaned = [re.sub(r"\s*---\s*$", "", t).strip() for t in cleaned]
    return [_strip_md(t) for t in cleaned] if cleaned else [_strip_md(raw)]


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
                    lines += ["", f"   👉 {_strip_md(a['insight'])}"]
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
                    blocks.append(_make_paragraph(f"👉 {_strip_md(a['insight'])}"))
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

    _S = "Georgia,'Times New Roman',Times,serif"
    _A = "Arial,Helvetica,sans-serif"
    _M = "'Century Gothic',CenturyGothic,AppleGothic,sans-serif"

    TAG_COLORS = {
        "플랫폼":            ("#EBF4FF", "#1A6BB5"),
        "배송/물류":         ("#FEF3E2", "#A06010"),
        "마케팅":            ("#FFEDEC", "#B83030"),
        "유한킴벌리 경쟁사": ("#F5EDF8", "#7B3FA0"),
        "기타":              ("#F3F4F6", "#6B7280"),
    }

    def make_tags(source: str, subcat: str) -> str:
        bg, fg = TAG_COLORS.get(subcat, ("#F3F4F6", "#6B7280"))
        return (
            f"<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin-bottom:6px;\"><tr>"
            f"<td style=\"background-color:{bg};padding:2px 8px;font-family:{_A};font-size:10px;"
            f"color:{fg};font-weight:bold;letter-spacing:0.04em;\">{esc(subcat)}</td>"
            f"<td width=\"6\"></td>"
            f"<td style=\"background-color:#F3F4F6;padding:2px 8px;font-family:{_A};font-size:10px;"
            f"color:#6B7280;font-weight:bold;letter-spacing:0.04em;\">{esc(source)}</td>"
            f"</tr></table>"
        )

    grouped = _group_articles(articles)

    # ── Highlight strip: 핵심 트렌드 ──
    highlights_html = ""
    for i, t in enumerate(insights):
        lines = [l for l in _strip_md(t).splitlines() if l.strip()]
        if not lines:
            continue
        bdr = "#C8B870" if i == 0 else "#888888"
        bg  = "#222222" if i == 0 else "#1E1E1E"
        tc  = "#C8B870" if i == 0 else "#AAAAAA"
        bc  = "#F0F0F0" if i == 0 else "#CCCCCC"
        title_line = esc(lines[0])
        body_text  = " ".join(esc(l) for l in lines[1:])
        body_part  = (
            f"<p style=\"margin:4px 0 0;font-family:{_S};font-size:12.5px;"
            f"color:{bc};line-height:1.6;\">{body_text}</p>"
            if body_text else ""
        )
        highlights_html += (
            f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" bgcolor=\"#1A1A1A\">"
            f"<tr><td bgcolor=\"#1A1A1A\" style=\"background-color:#1A1A1A;padding:0 24px 14px 24px;\">"
            f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            f"style=\"border-left:3px solid {bdr};background-color:{bg};\">"
            f"<tr><td style=\"padding:12px 16px;\">"
            f"<p style=\"margin:0;font-family:{_A};font-size:13px;font-weight:bold;"
            f"color:{tc};line-height:1.6;\">{title_line}</p>"
            f"{body_part}"
            f"</td></tr></table>"
            f"</td></tr></table>"
        )

    # ── Sections ──
    sections_html = ""
    article_num = 1

    for region in REGIONS:
        if region not in grouped:
            continue
        subcats = KR_SUBCATS if region == REGION_KR else GL_SUBCATS
        subcat_groups = grouped[region]
        ordered = [s for s in subcats if s in subcat_groups]
        extra   = [s for s in subcat_groups if s not in subcats]
        flat    = [(s, a) for s in ordered + extra for a in subcat_groups[s]]
        region_count = len(flat)

        sections_html += (
            f"<tr><td style=\"padding:32px 24px 0 24px;\">"
            f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
            f"<tr><td style=\"border-bottom:2px solid #0C0C0C;padding-bottom:8px;\">"
            f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\"><tr>"
            f"<td style=\"font-family:{_S};font-size:17px;font-weight:bold;color:#0C0C0C;\">{esc(region)}</td>"
            f"<td align=\"right\" style=\"font-family:{_A};font-size:11px;color:#AAAAAA;\">{region_count}건</td>"
            f"</tr></table>"
            f"</td></tr></table>"
            f"</td></tr>"
        )

        articles_html = ""
        for idx, (subcat, a) in enumerate(flat):
            is_last = (idx == len(flat) - 1)
            border  = "" if is_last else "border-bottom:1px solid #F0F0F0;"
            display_title = esc(_strip_md(a.get("title_ko") or a["title"]))
            num_str = f"{article_num:02d}"

            bullets_rows = ""
            for line in a["summary"].splitlines():
                line = line.strip()
                if not line:
                    continue
                content = line[2:] if line.startswith("- ") else line
                bullets_rows += (
                    f"<tr><td style=\"font-family:{_A};font-size:12.5px;"
                    f"color:#666666;line-height:1.7;padding:1px 0;\">"
                    f"· {esc(_strip_md(content))}</td></tr>"
                )

            insight_html = ""
            if a.get("insight"):
                insight_html = (
                    f"<p style=\"margin:8px 0 0;padding:8px 12px;"
                    f"background-color:#F8F6F0;border-left:2px solid #C8B870;"
                    f"font-family:{_A};font-size:12px;color:#374151;line-height:1.6;\">"
                    f"👉 {esc(_strip_md(a['insight']))}</p>"
                )

            articles_html += (
                f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"{border}\">"
                f"<tr>"
                f"<td width=\"32\" style=\"vertical-align:top;padding:16px 14px 14px 0;\">"
                f"<span style=\"font-family:{_A};font-size:11px;font-weight:bold;color:#C8B870;\">{num_str}</span>"
                f"</td>"
                f"<td style=\"padding:14px 0;\">"
                f"{make_tags(a['source'], subcat)}"
                f"<p style=\"margin:0 0 6px 0;font-family:{_S};font-size:14px;"
                f"font-weight:bold;color:#111111;line-height:1.5;\">{display_title}</p>"
                f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">{bullets_rows}</table>"
                f"{insight_html}"
                f"<p style=\"margin:8px 0 0;\">"
                f"<a href=\"{a['url']}\" style=\"font-family:{_A};font-size:11px;"
                f"color:#999999;text-decoration:none;\">원문 보기 →</a></p>"
                f"</td></tr></table>"
            )
            article_num += 1

        sections_html += (
            f"<tr><td style=\"padding:0 24px 24px 24px;\">{articles_html}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="ko" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<!--[if gte mso 9]>
<xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>
<![endif]-->
<style type="text/css">
  body, table, td, p, a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; border-collapse:collapse; }}
  body {{ margin:0; padding:0; background-color:#EDEAE2; }}
</style>
</head>
<body style="margin:0;padding:0;background-color:#EDEAE2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#EDEAE2;">
  <tr><td align="center" style="padding:28px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background-color:#ffffff;">

      <!-- HEADER -->
      <tr><td style="background-color:#0C0C0C;padding:32px 24px 24px 24px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="font-family:{_A};font-size:10px;letter-spacing:0.14em;color:#C8B870;text-transform:uppercase;font-weight:bold;">커머스 · 리테일 · 마케팅</td>
          <td align="right" style="font-family:{_A};font-size:11px;color:#666666;">{date_str}</td>
        </tr></table>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:18px;"><tr>
          <td style="font-family:{_M};font-size:36px;font-weight:bold;color:#FFFFFF;line-height:1.1;letter-spacing:-0.02em;">커머스<span style="color:#C8B870;">.</span><br>뉴스 트렌드</td>
        </tr></table>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;"><tr>
          <td style="font-family:{_A};font-size:11px;color:#666666;letter-spacing:0.08em;">이커머스 &nbsp;·&nbsp; 리테일 &nbsp;·&nbsp; 마케팅 핵심 요약</td>
        </tr></table>
      </td></tr>

      <!-- HIGHLIGHT STRIP -->
      <tr><td style="background-color:#1A1A1A;padding:0;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="font-family:{_A};font-size:10px;letter-spacing:0.13em;color:#C8B870;text-transform:uppercase;font-weight:bold;padding:18px 24px 12px 24px;">🔑 오늘의 핵심 트렌드</td>
        </tr></table>
        {highlights_html}
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="height:8px;"></td></tr></table>
      </td></tr>

      <!-- SECTIONS -->
      {sections_html}

      <!-- FOOTER -->
      <tr><td style="background-color:#F8F6F0;padding:24px 24px;border-top:1px solid #DDDDDD;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="font-family:{_A};font-size:11px;color:#AAAAAA;line-height:1.7;">자동 생성 &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; 커머스 뉴스 아카이버</td>
        </tr></table>
      </td></tr>

    </table>
  </td></tr>
</table>
</body></html>"""


# ── 이메일 발송 ──────────────────────────────────────────────────────────────
def send_email(articles: list[dict], date_str: str, insights: list[str]):
    if not RESEND_API_KEY:
        print("  [건너뜀] RESEND_API_KEY 없음")
        return
    if not EMAIL_FROM or not EMAIL_TO:
        print("  [건너뜀] EMAIL_FROM 또는 EMAIL_TO 없음")
        return

    to_addr  = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    bcc_addr = [e.strip() for e in EMAIL_BCC.split(",") if e.strip()]
    resend.api_key = RESEND_API_KEY
    html = _build_html(articles, date_str, insights)

    print(f"  [이메일] to {len(to_addr)}명 / bcc {len(bcc_addr)}명 발송 중...")
    params: resend.Emails.SendParams = {
        "from":    EMAIL_FROM,
        "to":      to_addr,
        "bcc":     bcc_addr,
        "subject": f"📦 커머스 브리핑 | {date_str}",
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
    articles = deduplicate_within_session(articles)
    articles = filter_hr_articles(articles)

    print("\n2/7  중복 필터링 (최근 4일 리포트 비교)")
    seen_urls, seen_titles = load_seen_records(days=4)
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
        print("\n" + "─" * 60)
        with open(filepath, encoding="utf-8") as f:
            print(f.read())
        print("─" * 60)
        print("\n[미리보기 모드] Notion 업로드 및 이메일 발송 건너뜀.")
    else:
        print("\n7/7  Notion 업로드 + 이메일 발송")
        try:
            upload_to_notion(articles, date_str, insights)
        except Exception as e:
            print(f"  [오류] Notion 업로드 실패: {e}")
        try:
            send_email(articles, date_str, insights)
        except Exception as e:
            print(f"  [오류] 이메일 발송 실패: {e}")

    print(f"\n✓ 완료! → {filepath}\n")


if __name__ == "__main__":
    main()
