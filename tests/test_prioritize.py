import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from news_archiver import prioritize_and_limit, REGION_KR, REGION_GL, KR_MAX, KR_OTHERS_RESERVED


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


_MAJOR = ["쿠팡", "컬리", "G마켓", "11번가", "무신사", "올리브영", "이마트", "홈플러스"]


def _major_articles():
    """주요 브랜드 8곳 × 2개 = 16개 — 예약 자리가 없으면 국내 12자리를 다 채우는 양"""
    return [_article(f"{b} 기사 {i}", f"KR-{b}") for b in _MAJOR for i in (1, 2)]


def test_others_get_reserved_slots():
    """주요 브랜드 기사가 넘쳐도 비우선 기사는 예약 자리만큼 들어간다"""
    others = [_article(f"SSG닷컴 기사 {i}", "KR-SSG") for i in range(6)]
    result = prioritize_and_limit(_major_articles() + others)
    kr = [a for a in result if a["region"] == REGION_KR]
    assert len(kr) == KR_MAX
    assert sum(a["source"] == "KR-SSG" for a in kr) == KR_OTHERS_RESERVED


def test_unused_reserved_slots_go_back_to_major_brands():
    """비우선 기사가 예약 자리보다 적으면 남는 자리는 주요 브랜드 기사가 채운다"""
    others = [_article("SSG닷컴 기사", "KR-SSG")]
    result = prioritize_and_limit(_major_articles() + others)
    kr = [a for a in result if a["region"] == REGION_KR]
    assert len(kr) == KR_MAX
    assert sum(a["source"] == "KR-SSG" for a in kr) == 1


def test_major_brands_listed_before_others():
    """출력 순서는 그대로 주요 브랜드 먼저"""
    others = [_article(f"SSG닷컴 기사 {i}", "KR-SSG") for i in range(6)]
    kr = [a for a in prioritize_and_limit(_major_articles() + others) if a["region"] == REGION_KR]
    first_other = next(i for i, a in enumerate(kr) if a["source"] == "KR-SSG")
    assert all(a["source"] == "KR-SSG" for a in kr[first_other:])


def test_reserved_slots_spread_across_feeds():
    """예약 자리는 피드 하나가 독차지하지 않고 피드별로 돌아가며 채운다"""
    others = ([_article(f"다이소 출시 {i}", "KR-다이소") for i in range(3)]
              + [_article("SSG닷컴 기사", "KR-SSG"),
                 _article("오늘의집 기사", "KR-오늘의집"),
                 _article("배민 기사", "KR-배민")])
    kr = [a for a in prioritize_and_limit(_major_articles() + others) if a["region"] == REGION_KR]
    picked = [a["source"] for a in kr if a["source"] in ("KR-다이소", "KR-SSG", "KR-오늘의집", "KR-배민")]
    assert sorted(picked) == ["KR-SSG", "KR-다이소", "KR-배민", "KR-오늘의집"]
