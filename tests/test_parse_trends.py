import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from news_archiver import _parse_trends


def test_parses_trend_blocks_and_strips_evidence_tag():
    raw = (
        "▶ 빠른배송 가격 경쟁이 커지고 있습니다. (근거: [15, 16])\n\n본문 1.\n\n"
        "▶ 판매자 지원이 확대되고 있습니다. (근거: [13, 18])\n\n본문 2."
    )
    result = _parse_trends(raw)
    assert len(result) == 2
    assert "근거" not in result[0]
    assert result[0].startswith("▶ 빠른배송")


def test_refusal_without_arrow_returns_empty():
    """2026-09-25: ▶ 없이 거절 설명만 온 경우 — 원문을 트렌드로 쓰면 안 된다."""
    raw = (
        "분석 결과, 제공된 기사들을 검토한 결과 산업 구조 변화를 뒷받침하는 "
        "명확한 트렌드를 도출하기 어렵습니다.\n\n권고사항\n- 더 많은 기사 필요"
    )
    assert _parse_trends(raw) == []


def test_refusal_inside_arrow_block_dropped():
    raw = "▶ 오늘은 명확한 트렌드를 도출하기 어렵습니다.\n\n기사가 분산되어 있습니다."
    assert _parse_trends(raw) == []


def test_trailing_recommendation_after_divider_cut():
    raw = "▶ 배송 경쟁이 커지고 있습니다.\n\n본문입니다.\n\n---\n\n참고: 추가 기사가 필요합니다."
    result = _parse_trends(raw)
    assert len(result) == 1
    assert "참고" not in result[0]


def test_empty_response_returns_empty():
    assert _parse_trends("") == []
