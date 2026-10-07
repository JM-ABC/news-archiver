import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kakao_notify import already_sent, mark_sent, parse_trend_file, select_representative, build_message, should_send, company_key, dedupe_by_company, classify_reply, verdict_from_replies, merge_candidates
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


def test_select_representative_takes_first_n_per_region():
    grouped = parse_trend_file(SAMPLE_TREND)
    kr, gl = select_representative(grouped, kr_n=2, gl_n=1)
    assert [a["title"] for a in kr] == ["쿠팡, 새벽배송 권역 전국 확대", "네이버쇼핑, 커머스 AI 기능 강화"]
    assert [a["title"] for a in gl] == ["Amazon, 신선식품 배송 확대"]


def test_select_representative_uses_all_when_fewer_than_n():
    grouped = parse_trend_file(SAMPLE_TREND)
    kr, gl = select_representative(grouped, kr_n=10, gl_n=5)
    assert len(kr) == 3
    assert len(gl) == 1


def test_build_message_format():
    kr = [
        {"title": "쿠팡, 새벽배송 권역 전국 확대", "insight": "시장 구도가 흔들립니다.", "summary": "", "url": "https://example.com/1"},
    ]
    gl = [
        {"title": "Amazon, 신선식품 배송 확대", "insight": "", "summary": "당일배송을 확대합니다.", "url": "https://example.com/4"},
    ]
    msg = build_message("2026-09-02", kr, gl)
    assert msg == (
        "📦 커머스 브리핑 5선 | 2026-09-02\n\n"
        "🇰🇷 국내\n"
        "1. 쿠팡, 새벽배송 권역 전국 확대\n"
        "시장 구도가 흔들립니다.\n"
        "https://example.com/1\n\n"
        "🌎 해외\n"
        "2. Amazon, 신선식품 배송 확대\n"
        "당일배송을 확대합니다.\n"
        "https://example.com/4"
    )


def test_should_send_requires_at_least_three_total():
    assert should_send([1], [1]) is False
    assert should_send([1, 1], [1]) is True
    assert should_send([1, 1, 1], []) is True


def test_normalize_newlines_treats_cr_as_lf():
    from kakao_notify import _normalize_newlines
    assert _normalize_newlines("첫줄\r\r둘째줄\r셋째줄") == "첫줄\n\n둘째줄\n셋째줄"
    assert _normalize_newlines("첫줄\r\n둘째줄") == "첫줄\n둘째줄"
    assert _normalize_newlines("첫줄\n둘째줄") == "첫줄\n둘째줄"


def test_single_instance_blocks_second_holder():
    from kakao_notify import acquire_single_instance
    name = "Local\\kakao_notify_test_single_instance"
    first = acquire_single_instance(name)
    assert first is not None
    assert acquire_single_instance(name) is None
    first.Close()
    again = acquire_single_instance(name)
    assert again is not None
    again.Close()


def test_paste_matches_ignores_newline_style_and_edges():
    from kakao_notify import _paste_matches
    assert _paste_matches("첫줄\n둘째줄", "첫줄\r둘째줄\r") is True
    assert _paste_matches("첫줄\n둘째줄", "첫줄") is False
    assert _paste_matches("첫줄", "") is False


def test_describe_mismatch_points_to_first_difference():
    from kakao_notify import _describe_mismatch
    note = _describe_mismatch("가나다라마바", "가나다X")
    assert "원본 6자" in note
    assert "입력창 4자" in note
    assert "4번째 글자" in note
    assert "'라마바'" in note
    assert "'X'" in note


def test_describe_mismatch_reports_truncated_paste():
    from kakao_notify import _describe_mismatch
    note = _describe_mismatch("가나다라", "가나")
    assert "3번째 글자" in note
    assert "''" in note


def test_is_effectively_empty_treats_placeholder_as_empty():
    from kakao_notify import _is_effectively_empty
    assert _is_effectively_empty("") is True
    assert _is_effectively_empty("   ") is True
    assert _is_effectively_empty("메시지 입력") is True
    assert _is_effectively_empty("아직 안 지워진 내용") is False


def _article(title, source=""):
    return {"title": title, "source": source, "insight": "", "summary": "", "url": ""}


def test_parse_trend_file_extracts_source_label():
    grouped = parse_trend_file(SAMPLE_TREND)
    assert [a["source"] for a in grouped[REGION_KR]] == ["KR-쿠팡", "KR-네이버쇼핑", "KR-컬리"]


def test_company_key_reads_title_or_source():
    assert company_key(_article("컬리, 떡·한과 판매 2배", "KR-컬리")) == "컬리"
    # 회사가 주어가 아니어도 제목에 이름이 있으면 잡는다
    assert company_key(_article("공정위, 갑질 혐의 CJ올리브영 현장 조사", "KR-유통정책")) == "올리브영"
    # 주제 피드로 들어온 회사 기사도 제목으로 잡는다
    assert company_key(_article("3년 만에 3배 뛴 무신사 몸값", "KR-패션뷰티")) == "무신사"


def test_company_key_returns_empty_for_unidentified():
    assert company_key(_article("추석 택배 물량 사상 최대", "KR-물류택배")) == ""


def test_dedupe_keeps_first_article_per_company():
    articles = [
        _article("컬리, 전통간식 매출 2배", "KR-컬리"),
        _article("K-디저트 인기…컬리, 떡·한과 2배", "KR-컬리"),
        _article("무신사 뷰티 홍대", "KR-무신사"),
        _article("3년 만에 3배 뛴 무신사 몸값", "KR-무신사"),
        _article("외국인 몰리는 CJ올리브영", "KR-올리브영"),
    ]
    assert [a["title"] for a in dedupe_by_company(articles)] == [
        "컬리, 전통간식 매출 2배",
        "무신사 뷰티 홍대",
        "외국인 몰리는 CJ올리브영",
    ]


def test_dedupe_keeps_all_unidentified_articles():
    """회사를 판별 못한 기사끼리는 묶지 않는다 — 정책·물류 기사가 통째로 사라지면 안 된다."""
    articles = [
        _article("추석 택배 물량 사상 최대", "KR-물류택배"),
        _article("전자상거래법 개정안 국회 통과", "KR-유통정책"),
    ]
    assert len(dedupe_by_company(articles)) == 2


def test_select_representative_skips_duplicate_company():
    grouped = {
        REGION_KR: [
            _article("컬리, 전통간식 매출 2배", "KR-컬리"),
            _article("K-디저트 인기…컬리, 떡·한과 2배", "KR-컬리"),
            _article("외국인 몰리는 CJ올리브영", "KR-올리브영"),
        ],
        REGION_GL: [],
    }
    kr, _ = select_representative(grouped, kr_n=2, gl_n=1)
    assert [a["title"] for a in kr] == ["컬리, 전통간식 매출 2배", "외국인 몰리는 CJ올리브영"]


def test_classify_reply_accepts_approval_words():
    assert classify_reply("발송") == "approve"
    assert classify_reply("ㅇㅇ") == "approve"
    assert classify_reply(" OK ") == "approve"
    assert classify_reply("발송!") == "approve"


def test_classify_reply_accepts_cancel_words():
    assert classify_reply("취소") == "cancel"
    assert classify_reply("ㄴㄴ") == "cancel"
    assert classify_reply("no") == "cancel"


def test_classify_reply_ignores_partial_match():
    """'발송하지마'를 승인으로 읽으면 정반대로 동작한다 — 전체 일치만 인정한다."""
    assert classify_reply("발송하지마") == ""
    assert classify_reply("취소할까 말까") == ""
    assert classify_reply("오늘 이거 괜찮은데?") == ""
    assert classify_reply("") == ""


def test_verdict_skips_parent_message():
    """messages[0]은 봇이 올린 안내문이다. 거기 '발송'이 있어도 승인이 아니다."""
    messages = [{"user": "UBOT", "text": "발송 또는 취소라고 답글을 달아주세요"}]
    assert verdict_from_replies(messages, "") == ""


def test_verdict_ignores_other_users():
    """채널의 다른 사람이 대신 승인해 버리면 안 된다."""
    messages = [
        {"user": "UBOT", "text": "안내문"},
        {"user": "UOTHER", "text": "발송"},
        {"user": "UME", "text": "취소"},
    ]
    assert verdict_from_replies(messages, "UME") == "cancel"


def test_verdict_takes_first_valid_reply():
    messages = [
        {"user": "UBOT", "text": "안내문"},
        {"user": "UME", "text": "잠깐만"},
        {"user": "UME", "text": "발송"},
    ]
    assert verdict_from_replies(messages, "UME") == "approve"


def test_verdict_without_approver_accepts_anyone():
    messages = [
        {"user": "UBOT", "text": "안내문"},
        {"user": "UANY", "text": "발송"},
    ]
    assert verdict_from_replies(messages, "") == "approve"


def test_verdict_empty_when_no_reply_yet():
    assert verdict_from_replies([{"user": "UBOT", "text": "안내문"}], "UME") == ""


def test_merge_candidates_catches_reply_posted_outside_thread():
    """2026-09-23 실사용 테스트에서 실제로 발생한 사례 —
    사용자가 스레드가 아니라 채널에 바로 '발송'이라고 쳐서 승인을 놓쳤다.
    스레드 답글이 비어 있어도 채널 메시지에서 판정을 찾아야 한다."""
    thread_messages = [{"user": "UBOT", "ts": "100.0", "text": "안내문"}]
    channel_messages = [
        {"user": "UBOT", "ts": "100.0", "text": "안내문"},
        {"user": "UME", "ts": "105.0", "text": "발송"},
    ]
    candidates = merge_candidates(thread_messages, channel_messages, "100.0")
    assert [m["text"] for m in candidates] == ["발송"]


def test_merge_candidates_orders_by_timestamp():
    thread_messages = [
        {"user": "UBOT", "ts": "100.0", "text": "안내문"},
        {"user": "UME", "ts": "110.0", "text": "잠깐만"},
    ]
    channel_messages = [
        {"user": "UBOT", "ts": "100.0", "text": "안내문"},
        {"user": "UME", "ts": "105.0", "text": "발송"},
    ]
    candidates = merge_candidates(thread_messages, channel_messages, "100.0")
    assert [m["text"] for m in candidates] == ["발송", "잠깐만"]


class _FakeUser32:
    def __init__(self, handle):
        self.handle = handle
        self.closed = []

    def OpenInputDesktop(self, flags, inherit, access):
        return self.handle

    def CloseDesktop(self, hdesk):
        self.closed.append(hdesk)


def test_is_screen_locked_true_when_input_desktop_unavailable():
    from kakao_notify import is_screen_locked
    assert is_screen_locked(_FakeUser32(0)) is True


def test_is_screen_locked_false_and_closes_handle_when_available():
    from kakao_notify import is_screen_locked
    fake = _FakeUser32(1234)
    assert is_screen_locked(fake) is False
    assert fake.closed == [1234]


# ── 슬랙 답글로 기사 교체 ─────────────────────────────────────────────────────
from kakao_notify import Briefing, parse_command, handle_replies, format_candidates


def _art(title, source):
    return {"title": title, "source": source, "insight": f"{title} 시사점", "summary": "", "url": f"https://ex.com/{title}"}


def _briefing():
    grouped = {
        REGION_KR: [
            _art("쿠팡 인삼", "KR-쿠팡"),          # 후보1
            _art("네이버 쇼핑탭", "KR-네이버쇼핑"),  # 후보2
            _art("컬리 넥스트키친", "KR-컬리"),      # 후보3
            _art("무신사 일본", "KR-무신사"),        # 후보4
            _art("쿠팡 로켓", "KR-쿠팡"),           # 후보5 (회사 중복)
            _art("올리브영 보라색", "KR-올리브영"),  # 후보6
            _art("컬리 카드", "KR-컬리"),           # 후보7
            _art("이마트 햇반", "KR-이마트"),        # 후보8
        ],
        REGION_GL: [
            _art("Amazon Prime", "GL-Amazon"),     # 후보9
            _art("Walmart+", "GL-Walmart"),        # 후보10
        ],
    }
    return Briefing("2026-10-07", grouped)


def _titles(b):
    return [a["title"] for a in b.articles(REGION_KR) + b.articles(REGION_GL)]


def test_briefing_starts_with_representative_selection():
    assert _titles(_briefing()) == ["쿠팡 인삼", "네이버 쇼핑탭", "컬리 넥스트키친", "무신사 일본", "Amazon Prime"]


def test_auto_replace_skips_company_already_in_briefing():
    b = _briefing()
    assert b.replace(3) == ""
    # 쿠팡 로켓은 1번 쿠팡과 겹치므로 건너뛰고 올리브영
    assert _titles(b)[2] == "올리브영 보라색"


def test_auto_replace_never_brings_back_removed_article():
    b = _briefing()
    b.replace(3)  # 컬리 넥스트키친 → 올리브영
    b.replace(3)  # 올리브영 → 컬리 카드 (넥스트키친으로 되돌아가지 않음)
    assert _titles(b)[2] == "컬리 카드"


def test_auto_replace_stays_in_region():
    b = _briefing()
    assert b.replace(5) == ""
    assert _titles(b)[4] == "Walmart+"
    assert b.replace(5) != ""  # 해외 후보가 더 없음
    assert _titles(b)[4] == "Walmart+"


def test_pick_specific_candidate():
    b = _briefing()
    assert b.replace(3, 8) == ""
    assert _titles(b)[2] == "이마트 햇반"


def test_pick_rejects_other_region_selected_or_unknown():
    b = _briefing()
    assert b.replace(3, 10) != ""   # 해외 후보를 국내 자리에
    assert b.replace(3, 1) != ""    # 이미 5선에 있는 기사
    assert b.replace(3, 99) != ""   # 없는 후보
    assert b.replace(9) != ""       # 없는 자리
    assert _titles(b)[2] == "컬리 넥스트키친"


def test_message_reflects_replacement():
    b = _briefing()
    b.replace(3, 6)
    msg = b.message()
    assert "올리브영 보라색" in msg and "컬리 넥스트키친" not in msg
    assert "3. 무신사 일본" not in msg and "3. 올리브영 보라색" in msg


def test_format_candidates_lists_unselected_with_stable_numbers():
    text = format_candidates(_briefing())
    assert "후보5. 쿠팡 로켓 (KR-쿠팡)" in text
    assert "후보10. Walmart+" in text
    assert "후보1." not in text and "후보9." not in text


def test_parse_command_variants():
    assert parse_command("발송") == ("approve",)
    assert parse_command("취소") == ("cancel",)
    assert parse_command("후보") == ("list",)
    assert parse_command("후보 목록") == ("list",)
    assert parse_command("3번 교체") == ("replace", 3, None)
    assert parse_command("3 교체") == ("replace", 3, None)
    assert parse_command("3번 바꿔줘") == ("replace", 3, None)
    assert parse_command("3번 → 후보7") == ("replace", 3, 7)
    assert parse_command("3번 -> 후보 7") == ("replace", 3, 7)
    assert parse_command("3번을 후보7로") == ("replace", 3, 7)
    assert parse_command("3번 후보7로 교체") == ("replace", 3, 7)


def test_parse_command_unescapes_slack_html():
    # 슬랙 API는 ">"를 "&gt;"로 보낸다 (2026-10-07 실사용 시험에서 발견)
    assert parse_command("3번 -&gt; 후보7") == ("replace", 3, 7)
    assert parse_command("3번 &gt; 후보7") == ("replace", 3, 7)
    assert parse_command("3번 =&gt; 후보7") == ("replace", 3, 7)


def test_parse_command_ignores_chatter():
    assert parse_command("컬리 넥스트 키친은 지난 번에 발송 했잖아") is None
    assert parse_command("3번 기사 별로네") is None
    assert parse_command("후보가 별로야") is None


def test_handle_replies_runs_each_command_once():
    b = _briefing()
    handled = set()
    replies = [{"ts": "1", "user": "UME", "text": "3번 교체"}]
    verdict, posts, changed = handle_replies(replies, handled, "UME", b)
    assert (verdict, changed, len(posts)) == ("", True, 1)
    # 다음 폴링에서 같은 답글을 또 읽어도 다시 실행하지 않는다
    verdict, posts, changed = handle_replies(replies, handled, "UME", b)
    assert (verdict, changed, posts) == ("", False, [])
    assert _titles(b)[2] == "올리브영 보라색"


def test_handle_replies_ignores_bot_and_other_users():
    b = _briefing()
    replies = [
        {"ts": "1", "bot_id": "B1", "text": "3번 교체"},
        {"ts": "2", "user": "UOTHER", "text": "3번 교체"},
        {"ts": "3", "user": "UOTHER", "text": "발송"},
    ]
    verdict, posts, changed = handle_replies(replies, set(), "UME", b)
    assert (verdict, changed, posts) == ("", False, [])


def test_handle_replies_replace_then_approve_in_one_poll():
    b = _briefing()
    replies = [
        {"ts": "1", "user": "UME", "text": "후보"},
        {"ts": "2", "user": "UME", "text": "3번 → 후보8"},
        {"ts": "3", "user": "UME", "text": "발송"},
    ]
    verdict, posts, changed = handle_replies(replies, set(), "UME", b)
    assert verdict == "approve" and changed and len(posts) == 2
    assert "이마트 햇반" in b.message()


def test_handle_replies_reports_error_without_change():
    b = _briefing()
    verdict, posts, changed = handle_replies([{"ts": "1", "user": "UME", "text": "3번 → 후보10"}], set(), "", b)
    assert verdict == "" and not changed and "국내" in posts[0]


def test_handle_replies_without_briefing_explains():
    verdict, posts, changed = handle_replies([{"ts": "1", "user": "UME", "text": "3번 교체"}], set(), "", None)
    assert verdict == "" and not changed and "바꿀 수 없어요" in posts[0]
