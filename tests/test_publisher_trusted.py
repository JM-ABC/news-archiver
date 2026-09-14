import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from news_archiver import _publisher_trusted, RSS_FEEDS


def test_trusted_domain_with_and_without_www():
    assert _publisher_trusted("techcrunch.com")
    assert _publisher_trusted("www.adweek.com")
    assert _publisher_trusted("WWW.Reuters.com")


def test_untrusted_domains_from_2026_09_14():
    """사용자가 품질 저하로 지적한 매체는 통과하지 못한다."""
    for host in ["www.upi.com", "www.ecommercebytes.com", "finance.biggo.com"]:
        assert not _publisher_trusted(host), host


def test_subdomain_not_auto_trusted():
    """businessinsider.com은 허용해도 보도자료 서브도메인은 막는다."""
    assert _publisher_trusted("www.businessinsider.com")
    assert not _publisher_trusted("markets.businessinsider.com")


def test_empty_domain_not_trusted():
    assert not _publisher_trusted("")


def test_trusted_only_applies_to_global_google_news_feeds_only():
    """국내 피드와 전문지 직접 RSS에는 허용 목록이 걸리지 않는다."""
    flagged = [f["label"] for f in RSS_FEEDS if f.get("trusted_only")]
    assert len(flagged) == 6
    for f in RSS_FEEDS:
        if f.get("trusted_only"):
            assert f["label"].startswith("GL-"), f["label"]
            assert "news.google.com" in f["url"], f["label"]
