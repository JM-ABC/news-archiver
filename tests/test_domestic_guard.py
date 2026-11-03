import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import news_archiver
from news_archiver import REGION_KR, REGION_GL


def _article(title, region):
    return {"title": title, "url": f"https://example.com/{title}", "source": "X", "region": region}


def test_no_domestic_articles_stops_before_summarize(monkeypatch):
    """국내 0건이면 요약·발송 전에 실패로 종료한다 (2026-10-26 해외판 발송 재발 방지)"""
    monkeypatch.setattr(news_archiver, "fetch_articles",
                        lambda: [_article(f"global {i}", REGION_GL) for i in range(15)])
    called = []
    monkeypatch.setattr(news_archiver, "summarize_articles", lambda a: called.append(a) or a)
    with pytest.raises(SystemExit) as e:
        news_archiver.main()
    assert e.value.code == 1
    assert not called


def test_domestic_present_passes_guard(monkeypatch):
    """국내 기사가 1건이라도 있으면 다음 단계로 넘어간다"""
    articles = [_article("국내 1", REGION_KR)] + [_article(f"global {i}", REGION_GL) for i in range(3)]
    monkeypatch.setattr(news_archiver, "fetch_articles", lambda: articles)
    reached = []
    monkeypatch.setattr(news_archiver, "deduplicate_within_session", lambda a: reached.append(1) or [])
    monkeypatch.setattr(news_archiver, "load_seen_records", lambda days: (set(), set()))
    with pytest.raises(SystemExit) as e:
        news_archiver.main()
    assert reached
    assert e.value.code == 0  # 기사 수 미달로 조용히 종료 — 국내 검사는 통과
