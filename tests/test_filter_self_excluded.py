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


# ── 조사 차이 대응 (2026-09-14 미리보기에서 5건 통과한 사례) ──────────────────
def test_excludes_파급력이_제한적_조사만_다른_경우():
    """키워드는 '파급력은'인데 Claude가 '파급력이'로 써도 제외된다."""
    articles = [
        _article("SoHo", "이 항목은 부동산·상권 분석 차원의 일반 뉴스로 커머스 업계 파급력이 제한적입니다."),
        _article("Nori", "이 항목은 개별 브랜드의 성공사례로 업계 전반의 파급력이 제한적입니다."),
        _article("정상", "쿠팡의 배송망 확대는 경쟁사 물류 투자를 앞당깁니다."),
    ]
    result = filter_self_excluded(articles)
    assert [a["title"] for a in result] == ["정상"]


def test_excludes_other_particles():
    """은/는/이/가 어느 조사를 써도 같은 키워드로 취급한다."""
    for insight in ["산업 영향이 제한적입니다.", "파장이 제한적입니다.", "거리는 있습니다."]:
        assert filter_self_excluded([_article("x", insight)]) == [], insight


def test_particle_relaxation_does_not_catch_normal_insights():
    """조사를 풀었다고 해서 '파급력이 크다' 같은 정상 시사점까지 잡으면 안 된다."""
    articles = [
        _article("A", "이 조치의 파급력이 큽니다."),
        _article("B", "공급 제한적 상황이 이어집니다."),
        _article("C", "업계 거리두기가 강화됩니다."),
    ]
    assert len(filter_self_excluded(articles)) == 3


# ── 2026-09-25: "(제외 - 기타)" 제목이 기사로 발송된 사례 ─────────────────────
def test_excludes_제외_placeholder_title():
    a = _article("원제목", "")
    a["title_ko"] = "(제외 - 기타)"
    a["summary"] = "별도 처리 불가능한 뉴스입니다."
    assert filter_self_excluded([a]) == []


def test_excludes_paraphrased_exclusion_verdicts():
    """키워드 그대로가 아닌 제외 판정 문구도 잡는다 (2026-10-07: 5건 발송됨)."""
    verdicts = [
        "제외 기준에 해당하여 상세 분석 대상 제외 처리합니다.",
        "본 항목은 스포츠 행사 보도로 제외 범위에 해당합니다.",
        "제외 대상입니다. 특정 문화 이벤트 중심의 마케팅 사례로",
        "단순 통계 정리로 분류되어 제외 대상에 해당하나, 필요시",
        "정치 뉴스에 해당하므로 분석 대상에서 제외됩니다.",
        "커머스 산업 동향 분석의 우선순위에서 제외됩니다.",
        "소비자 가이드 성격으로, 주요 뉴스 대상에서 제외됩니다.",
        "[제외 - 단순 임원 교체 뉴스]",
        "대상 제외",
    ]
    articles = [_article(f"기사 {i}", v) for i, v in enumerate(verdicts)]
    assert filter_self_excluded(articles) == []


def test_keeps_normal_insights_mentioning_exclusion():
    """'제외'가 들어가도 판정 문구가 아니면 남긴다."""
    normal = [
        "대형마트가 의무휴업 규제 대상에서 제외되면서 새벽배송 경쟁이 심화됩니다.",
        "쿠팡을 제외한 플랫폼들의 점유율이 정체되고 있습니다.",
        "환율 영향을 제외하면 매출 성장률은 둔화됐습니다.",
        "PB 상품이 할인 행사 적용 대상에서 제외돼 가격 경쟁력이 약해질 수 있습니다.",
    ]
    articles = [_article(f"기사 {i}", v) for i, v in enumerate(normal)]
    assert len(filter_self_excluded(articles)) == len(normal)
