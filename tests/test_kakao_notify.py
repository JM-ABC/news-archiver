import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kakao_notify import already_sent, mark_sent, parse_trend_file
from news_archiver import REGION_KR, REGION_GL


SAMPLE_TREND = """커머스 뉴스 트렌드 | 2026-09-02
---

🔑 오늘의 핵심 트렌드

▶ 예시 트렌드

내용

---
🇰🇷 국내 뉴스
---

[ 플랫폼 ]

① 쿠팡, 새벽배송 권역 전국 확대
   출처: KR-쿠팡

   - 쿠팡이 새벽배송 권역을 전국으로 확대합니다.
   - 물류센터 20곳을 신규 가동합니다.

   👉 대형마트 새벽배송 규제가 풀리면서 시장 구도가 흔들릴 가능성이 커지고 있습니다.

   원문: https://example.com/1
---

② 네이버쇼핑, 커머스 AI 기능 강화
   출처: KR-네이버쇼핑

   - 네이버가 쇼핑 검색에 AI 추천을 도입합니다.

   👉 검색 기반 커머스 경쟁이 심화됩니다.

   원문: https://example.com/2
---

[ 배송/물류 ]

③ 컬리, 물류센터 증설
   출처: KR-컬리

   - 컬리가 물류센터를 증설합니다.

   👉 새벽배송 경쟁이 격화됩니다.

   원문: https://example.com/3
---
🌎 글로벌 뉴스
---

[ 플랫폼 ]

④ Amazon, 신선식품 배송 확대
   출처: GL-메가유통

   - Amazon이 신선식품 당일배송을 확대합니다.

   👉 그로서리 시장 경쟁이 심화됩니다.

   원문: https://example.com/4
---
생성: 2026-09-02 08:03:11"""


def test_parse_trend_file_splits_by_region():
    grouped = parse_trend_file(SAMPLE_TREND)
    assert len(grouped[REGION_KR]) == 3
    assert len(grouped[REGION_GL]) == 1


def test_parse_trend_file_extracts_fields_in_order():
    grouped = parse_trend_file(SAMPLE_TREND)
    first = grouped[REGION_KR][0]
    assert first["title"] == "쿠팡, 새벽배송 권역 전국 확대"
    assert first["insight"] == "대형마트 새벽배송 규제가 풀리면서 시장 구도가 흔들릴 가능성이 커지고 있습니다."
    assert first["url"] == "https://example.com/1"
    assert grouped[REGION_KR][1]["title"] == "네이버쇼핑, 커머스 AI 기능 강화"


def test_parse_trend_file_falls_back_to_first_bullet_when_no_insight():
    text = SAMPLE_TREND.replace(
        "   👉 대형마트 새벽배송 규제가 풀리면서 시장 구도가 흔들릴 가능성이 커지고 있습니다.\n\n",
        "",
    )
    grouped = parse_trend_file(text)
    assert grouped[REGION_KR][0]["insight"] == ""
    assert grouped[REGION_KR][0]["summary"] == "쿠팡이 새벽배송 권역을 전국으로 확대합니다."


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
