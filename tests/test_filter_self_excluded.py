import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from news_archiver import filter_self_excluded, REGION_KR


def _article(title, insight="", source="KR-테스트"):
    return {
        "title": title,
        "title_ko": "",
        "url": f"https://example.com/{title}",
        "source": source,
        "region": REGION_KR,
        "subcategory": "기타",
        "summary": "",
        "insight": insight,
    }


def test_no_exclusion_keywords_keeps_all():
    """제외 키워드가 없는 기사는 모두 유지된다."""
    articles = [
        _article("기사 1", "이 기사는 중요합니다."),
        _article("기사 2", "시장 변화가 나타나고 있습니다."),
    ]
    result = filter_self_excluded(articles)
    assert len(result) == 2


def test_excludes_산업_분석_대상에서_제외():
    articles = [
        _article("제외 기사", "산업 분석 대상에서 제외"),
        _article("유지 기사", "중요한 시사점입니다."),
    ]
    result = filter_self_excluded(articles)
    assert len(result) == 1
    assert result[0]["title"] == "유지 기사"


def test_excludes_커머스_채널_전략과_무관():
    articles = [
        _article("기사 A", "커머스 채널 전략과 무관한 내용입니다."),
        _article("기사 B", "채널 전략에 영향을 줍니다."),
    ]
    result = filter_self_excluded(articles)
    assert len(result) == 1
    assert result[0]["title"] == "기사 B"


def test_excludes_산업_뉴스_범주에서_제외():
    articles = [_article("기사 X", "산업 뉴스 범주에서 제외됩니다.")]
    result = filter_self_excluded(articles)
    assert len(result) == 0


def test_excludes_제외합니다():
    articles = [
        _article("기사 Y", "이 기사는 제외합니다."),
        _article("기사 Z", "이 기사는 포함됩니다."),
    ]
    result = filter_self_excluded(articles)
    assert len(result) == 1
    assert result[0]["title"] == "기사 Z"


def test_empty_insight_not_excluded():
    """insight가 빈 문자열이면 제외하지 않는다."""
    articles = [_article("기사 1", ""), _article("기사 2")]
    result = filter_self_excluded(articles)
    assert len(result) == 2


def test_multiple_excluded_simultaneously():
    """여러 기사가 동시에 제외된다."""
    articles = [
        _article("기사 1", "산업 분석 대상에서 제외"),
        _article("기사 2", "커머스 채널 전략과 무관"),
        _article("기사 3", "정상 기사입니다."),
    ]
    result = filter_self_excluded(articles)
    assert len(result) == 1
    assert result[0]["title"] == "기사 3"


def test_slots_not_filled_after_exclusion():
    """제외 후 빈 슬롯은 채우지 않는다 — 결과 수가 줄어야 한다."""
    articles = [_article(f"기사 {i}", "") for i in range(5)]
    articles[2]["insight"] = "제외합니다."
    result = filter_self_excluded(articles)
    assert len(result) == 4
