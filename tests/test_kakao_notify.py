import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kakao_notify import already_sent, mark_sent


def test_not_sent_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("kakao_notify.TRENDS_DIR", str(tmp_path))
    assert already_sent("2026-09-02") is False


def test_mark_sent_then_already_sent(tmp_path, monkeypatch):
    monkeypatch.setattr("kakao_notify.TRENDS_DIR", str(tmp_path))
    mark_sent("2026-09-02")
    assert already_sent("2026-09-02") is True


def test_different_date_not_affected(tmp_path, monkeypatch):
    monkeypatch.setattr("kakao_notify.TRENDS_DIR", str(tmp_path))
    mark_sent("2026-09-02")
    assert already_sent("2026-09-04") is False
