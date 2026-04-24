import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from news_archiver import prioritize_and_limit, REGION_KR, REGION_GL, KR_MAX


def _article(title, source, region=REGION_KR):
    return {
        "title": title,
        "title_ko": "",
        "url": f"https://example.com/{title}",
        "source": source,
        "region": region,
        "subcategory": "기타",
        "summary": "",
        "insight": "",
    }


def test_per_brand_max_coupang():
    """쿠팡 기사 5개 풀 → 결과에서 쿠팡 기사 최대 2개"""
    articles = [_article(f"쿠팡 뉴스 {i}", "KR-쿠팡") for i in range(5)]
    result = prioritize_and_limit(articles)
    coupang = [a for a in result if "쿠팡" in a["title"] or "쿠팡" in a["source"]]
    assert len(coupang) <= 2


def test_overflow_excluded_even_with_empty_slots():
    """top+others가 limit 미만이어도 overflow는 결과에 포함되지 않는다"""
    articles = [
        _article("쿠팡 기사 1", "KR-쿠팡"),
        _article("쿠팡 기사 2", "KR-쿠팡"),
    ] + [_article(f"쿠팡 overflow {i}", "KR-쿠팡") for i in range(5)]
    result = prioritize_and_limit(articles)
    overflow_in_result = [a for a in result if "overflow" in a["title"]]
    assert len(overflow_in_result) == 0


def test_overflow_excluded_when_slots_full():
    """top+others가 limit를 채워도 overflow는 포함되지 않는다"""
    articles = []
    brands = ["쿠팡", "네이버", "컬리", "G마켓", "11번가", "무신사", "올리브영"]
    for brand in brands:
        articles.append(_article(f"{brand} 기사 1", f"KR-{brand}"))
        articles.append(_article(f"{brand} 기사 2", f"KR-{brand}"))
    articles += [_article(f"쿠팡 overflow {i}", "KR-쿠팡") for i in range(3)]
    result = prioritize_and_limit(articles)
    overflow_in_result = [a for a in result if "overflow" in a["title"]]
    assert len(overflow_in_result) == 0
