"""
커머스 브리핑 카톡 자동 발송 봇
- trends/trend_YYYY-MM-DD.txt에서 대표 5개(국내 4 + 해외 1) 추출
- 발송 전 사람 승인 팝업 → 승인 시에만 카카오톡 PC 앱으로 전송
- 실패/취소 시 이메일로 알림
"""

import ctypes
import os
import re
import sys
import time
import datetime
import subprocess
import tkinter as tk

import requests
import resend
import win32api
import win32clipboard
import win32event
import winerror
from dotenv import load_dotenv
from pywinauto import Desktop

from news_archiver import REGION_KR, REGION_GL

load_dotenv()

TRENDS_DIR = os.getenv("TRENDS_DIR", "./trends")
KAKAO_CHATROOM_NAME = os.getenv("KAKAO_CHATROOM_NAME", "")
KAKAO_APPROVAL_TIMEOUT_MIN = int(os.getenv("KAKAO_APPROVAL_TIMEOUT_MIN", "30"))
DRY_RUN = "--dry-run" in sys.argv
# 승인 경로만 시험한다 (실제 카톡 발송 없음). 슬랙 설정 직후 확인용.
TEST_APPROVAL = "--test-approval" in sys.argv
# 붙여넣기 검증만 시험한다 — 실제 채팅방 입력창에 붙였다가 Enter 없이 비운다.
TEST_PASTE = "--test-paste" in sys.argv

# 슬랙 승인 — 설정돼 있으면 PC 팝업 대신 슬랙 스레드 답글로 승인받는다.
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APPROVAL_CHANNEL = os.getenv("SLACK_APPROVAL_CHANNEL", "")
SLACK_APPROVER_USER_ID = os.getenv("SLACK_APPROVER_USER_ID", "")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO", "")

KST = datetime.timezone(datetime.timedelta(hours=9))

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def git_pull() -> bool:
    print("  [git] 최신 리포트 가져오는 중...")
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        print(f"  [git] pull 실패: {e}")
        return False
    if result.returncode != 0:
        print(f"  [git] pull 실패:\n{result.stdout}\n{result.stderr}")
        return False
    print(f"  [git] {result.stdout.strip() or '최신 상태'}")
    return True


def today_str() -> str:
    return datetime.datetime.now(KST).strftime("%Y-%m-%d")


def _marker_path(date_str: str) -> str:
    return os.path.join(TRENDS_DIR, f".kakao_sent_{date_str}")


def already_sent(date_str: str) -> bool:
    return os.path.exists(_marker_path(date_str))


_INSTANCE_MUTEX_NAME = "Local\\news_archiver_kakao_notify"


def acquire_single_instance(name: str = _INSTANCE_MUTEX_NAME):
    """봇이 이미 돌고 있으면 None을 반환한다.

    2026-09-30: 예약 실행(11:20:00)과 수동 실행(11:20:01)이 겹쳐 둘 다
    already_sent()를 통과했고, 채널에 친 "발송" 한 번이 두 승인 요청을 모두
    승인해 카톡이 두 번 나갔다. 윈도우 이름 있는 뮤텍스는 프로세스가 죽으면
    자동으로 풀리므로, 잠금 파일과 달리 비정상 종료 뒤에 남아 막는 일이 없다.
    반환된 핸들을 프로세스가 끝날 때까지 들고 있어야 잠금이 유지된다."""
    handle = win32event.CreateMutex(None, False, name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        handle.Close()
        return None
    return handle


def mark_sent(date_str: str) -> None:
    os.makedirs(TRENDS_DIR, exist_ok=True)
    with open(_marker_path(date_str), "w", encoding="utf-8") as f:
        f.write(datetime.datetime.now(KST).isoformat())


# news_archiver.py의 _CIRCLE 리스트(①~㉚, 30개)와 짝을 맞춘 패턴이다.
# KR_MAX + GL_MAX가 30을 넘으면 news_archiver.circle_num()이 "(31)" 같은 일반 텍스트로
# 넘어가므로, 그 경우 이 정규식이 매칭하지 못해 해당 기사가 조용히 파싱에서 누락된다.
_CIRCLE_RE = re.compile(r"^[①-⑳㉑-㉚]\s+(.+)$")


def parse_trend_file(text: str) -> dict:
    """trend_YYYY-MM-DD.txt 본문을 리전별 기사 목록으로 파싱한다.

    각 기사는 {"title", "source", "insight", "summary", "url"} 딕셔너리.
    insight는 👉 시사점 문장, summary는 첫 요약 불렛(insight가 없을 때의 대체용).
    source는 "출처:" 라인의 피드 라벨(예: "KR-컬리") — 회사 중복 제거에 쓴다.
    """
    grouped = {REGION_KR: [], REGION_GL: []}
    region = None
    current = None
    current_region = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line == REGION_KR:
            region = REGION_KR
            continue
        if line == REGION_GL:
            region = REGION_GL
            continue

        m = _CIRCLE_RE.match(line)
        if m and region:
            current = {"title": m.group(1).strip(), "source": "", "insight": "", "summary": "", "url": ""}
            current_region = region
            continue

        if current is None:
            continue

        if line.startswith("출처:"):
            current["source"] = line.split("출처:", 1)[1].strip()
        elif line.startswith("👉"):
            current["insight"] = line.split("👉", 1)[1].strip()
        elif line.startswith("- ") and not current["summary"]:
            current["summary"] = line[2:].strip()
        elif line.startswith("원문:"):
            current["url"] = line.split("원문:", 1)[1].strip()
            grouped[current_region].append(current)
            current = None

    return grouped


# 5선에 같은 회사 기사가 두 번 들어가는 것을 막기 위한 회사 키 목록이다.
# 2026-09-11 리포트에서 컬리 전통간식 기사 2건이 5선 중 2칸을 차지한 것이 계기다.
# news_archiver.RSS_FEEDS의 "회사별" 피드 라벨과 짝을 맞춘다 — KR-이커머스,
# KR-패션뷰티, KR-유한킴벌리(경쟁사) 같은 주제 피드 라벨은 서로 다른 회사 기사가
# 섞여 들어오므로 일부러 넣지 않았다. 넣으면 다른 회사 기사가 중복으로 잘못 잡힌다.
_COMPANY_KEYWORDS = (
    "쿠팡", "네이버", "컬리", "무신사", "올리브영", "이마트", "홈플러스",
    "롯데마트", "롯데온", "11번가", "G마켓", "다이소", "카카오", "티몬",
    "위메프", "배민", "29CM", "당근", "SSG", "더현대", "CJ온스타일",
    "GS리테일", "오늘의집", "지그재그", "아모레", "LGH&H",
)


def company_key(article: dict) -> str:
    """기사의 주체 회사를 식별한다. 판별 불가면 빈 문자열.

    제목과 출처 라벨을 함께 본다. 제목만 보면 "공정위, 갑질 혐의 CJ올리브영
    현장 조사"처럼 회사가 주어가 아닌 기사를 놓치고, 출처만 보면 KR-패션뷰티
    같은 주제 피드로 들어온 회사 기사를 놓치기 때문이다.
    시사점(insight)은 보지 않는다 — 경쟁사 이름이 자주 등장해 오탐이 난다.
    """
    haystack = f"{article.get('title', '')} {article.get('source', '')}"
    for keyword in _COMPANY_KEYWORDS:
        if keyword in haystack:
            return keyword
    return ""


def dedupe_by_company(articles: list) -> list:
    """같은 회사 기사는 리포트에서 먼저 나온 1건만 남긴다.
    회사를 판별하지 못한 기사(company_key가 빈 문자열)는 서로 묶지 않고 모두 남긴다 —
    정책·물류 기사가 한 덩어리로 뭉뚱그려져 사라지는 것을 막기 위한 보수적 선택이다."""
    seen = set()
    result = []
    for article in articles:
        key = company_key(article)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(article)
    return result


def select_representative(grouped: dict, kr_n: int = 4, gl_n: int = 1):
    kr = dedupe_by_company(grouped.get(REGION_KR, []))[:kr_n]
    gl = dedupe_by_company(grouped.get(REGION_GL, []))[:gl_n]
    return kr, gl


def should_send(kr_articles: list, gl_articles: list) -> bool:
    return (len(kr_articles) + len(gl_articles)) >= 3


def _one_liner(article: dict) -> str:
    return article["insight"] or article["summary"] or "(요약 없음)"


def build_message(date_str: str, kr_articles: list, gl_articles: list) -> str:
    lines = [f"📦 커머스 브리핑 5선 | {date_str}", ""]
    num = 1

    if kr_articles:
        lines.append("🇰🇷 국내")
        for a in kr_articles:
            lines.append(f"{num}. {a['title']}")
            lines.append(_one_liner(a))
            lines.append(a["url"])
            lines.append("")
            num += 1

    if gl_articles:
        lines.append("🌎 해외")
        for a in gl_articles:
            lines.append(f"{num}. {a['title']}")
            lines.append(_one_liner(a))
            lines.append(a["url"])
            lines.append("")
            num += 1

    return "\n".join(lines).rstrip()


_DESKTOP_SWITCHDESKTOP = 0x0100

LOCKED_NOTICE = (
    "봇이 도는 PC의 화면이 잠겨 있어 카톡 입력창을 조작할 수 없습니다. "
    "PC 잠금을 풀고 `python kakao_notify.py`를 다시 실행하세요."
)


def is_screen_locked(user32=None) -> bool:
    """화면이 잠겨 있으면 True. 잠금 중에는 입력 데스크톱이 로그온 화면으로 바뀌어
    OpenInputDesktop이 실패한다.

    2026-10-02: 다른 노트북에서 슬랙 승인을 눌렀는데 봇 PC가 잠겨 있어 붙여넣기 검증이
    "입력창 6자(메시지 입력)"로 실패했다. 화면 조작 방식이라 잠금 중에는 전송할 수 없다."""
    user32 = user32 or ctypes.windll.user32
    hdesk = user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
    if not hdesk:
        return True
    user32.CloseDesktop(hdesk)
    return False


def notify_slack(text: str) -> None:
    """승인 채널에 알림을 남긴다. 실패해도 본 흐름을 막지 않는다."""
    if not slack_configured():
        return
    try:
        _slack_request("chat.postMessage", "POST", {
            "channel": SLACK_APPROVAL_CHANNEL,
            "text": text,
        })
    except SlackApprovalError as e:
        print(f"  [슬랙] 알림 실패: {e}")


def notify_failure(date_str: str, reason: str, message: str = "") -> None:
    print(f"  [알림] 카톡 발송 실패/취소 — {reason}")
    if not RESEND_API_KEY or not EMAIL_FROM or not EMAIL_TO:
        print("  [알림] RESEND_API_KEY/EMAIL_FROM/EMAIL_TO 미설정 — 이메일 알림 건너뜀")
        return

    to_addr = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    resend.api_key = RESEND_API_KEY
    body = f"사유: {reason}\n\n--- 준비된 메시지 ---\n{message}" if message else f"사유: {reason}"
    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": to_addr,
            "subject": f"⚠️ 카톡 브리핑 발송 실패 | {date_str}",
            "text": body,
        })
    except Exception as e:
        print(f"  [알림] 이메일 발송도 실패: {e}")


def show_confirmation(message: str, timeout_min: int) -> bool:
    """메시지 미리보기를 보여주고 [발송]/[취소] 승인을 받는다.
    timeout_min 안에 응답이 없으면 False(취소)를 반환한다."""
    result = {"approved": False}
    root = tk.Tk()
    root.title("커머스 브리핑 카톡 발송 확인")
    root.geometry("480x480")
    root.minsize(420, 360)
    root.attributes("-topmost", True)

    def on_approve():
        result["approved"] = True
        root.destroy()

    def on_cancel():
        result["approved"] = False
        root.destroy()

    # 버튼/카운트다운을 먼저 하단에 고정 배치한다. 메시지 본문(Text)을 나중에
    # fill+expand로 채우면, 메시지가 길어 창 높이를 넘어가도 버튼이 창 밖으로
    # 밀려나 안 보이는 일 없이 항상 하단에 남는다.
    button_frame = tk.Frame(root)
    button_frame.pack(side="bottom", pady=12)
    tk.Button(button_frame, text="발송", width=12, bg="#111111", fg="white", command=on_approve).pack(side="left", padx=8)
    tk.Button(button_frame, text="취소", width=12, command=on_cancel).pack(side="left", padx=8)

    countdown_label = tk.Label(root, text="", fg="gray")
    countdown_label.pack(side="bottom")

    tk.Label(root, text="아래 메시지를 오픈채팅방에 발송할까요?", font=("맑은 고딕", 11, "bold")).pack(side="top", pady=(12, 4))

    # height를 명시하지 않으면 Text 위젯 기본값(24줄)이 적용돼 창이 화면보다
    # 커져 버튼이 화면 밖으로 밀려날 수 있다 — 실제 팝업 테스트에서 발견됨.
    text_widget = tk.Text(root, wrap="word", font=("맑은 고딕", 10), height=16)
    text_widget.insert("1.0", message)
    text_widget.config(state="disabled")
    text_widget.pack(side="top", fill="both", expand=True, padx=12, pady=8)

    remaining = {"seconds": timeout_min * 60}

    def tick():
        if remaining["seconds"] <= 0:
            on_cancel()
            return
        mins, secs = divmod(remaining["seconds"], 60)
        countdown_label.config(text=f"{mins}분 {secs}초 안에 응답이 없으면 자동 취소됩니다.")
        remaining["seconds"] -= 1
        root.after(1000, tick)

    root.after(1000, tick)
    root.mainloop()
    return result["approved"]


# ── 슬랙 승인 ────────────────────────────────────────────────────────────────
# 슬랙 버튼(Block Kit)은 클릭을 받아줄 공개 URL이 있어야 해서 쓸 수 없다.
# 대신 미리보기를 올리고, 그 스레드에 달리는 답글 한 줄로 승인받는다.
_SLACK_API = "https://slack.com/api/"
_SLACK_POLL_SEC = 5

_APPROVE_WORDS = {"발송", "ㅇ", "ㅇㅇ", "ok", "o", "yes", "y", "go"}
_CANCEL_WORDS = {"취소", "ㄴ", "ㄴㄴ", "no", "n", "x", "cancel"}


class SlackApprovalError(Exception):
    pass


def slack_configured() -> bool:
    return bool(SLACK_BOT_TOKEN and SLACK_APPROVAL_CHANNEL)


def _slack_request(method: str, http: str, payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    try:
        if http == "GET":
            resp = requests.get(_SLACK_API + method, headers=headers, params=payload, timeout=15)
        else:
            resp = requests.post(_SLACK_API + method, headers=headers, json=payload, timeout=15)
        data = resp.json()
    except Exception as e:
        raise SlackApprovalError(f"{method} 호출 실패: {e}") from e
    if not data.get("ok"):
        raise SlackApprovalError(f"{method} 오류: {data.get('error', '알 수 없음')}")
    return data


def classify_reply(text: str) -> str:
    """답글 한 줄을 'approve' / 'cancel' / '' 로 판정한다.

    부분 일치가 아니라 전체 일치로 본다. "발송하지마"에 '발송'이 들어있다고
    승인으로 읽으면 정반대로 동작하기 때문이다.
    """
    token = (text or "").strip().strip(".!?~ ").lower()
    if token in _APPROVE_WORDS:
        return "approve"
    if token in _CANCEL_WORDS:
        return "cancel"
    return ""


def verdict_from_replies(messages: list, approver_id: str) -> str:
    """스레드 답글 목록에서 최종 판정을 뽑는다. 판정 불가면 빈 문자열.

    messages[0]은 봇이 올린 원본이라 건너뛴다. approver_id가 설정돼 있으면
    그 사람의 답글만 인정한다 — 채널의 다른 사람이 대신 승인하는 것을 막는다.
    """
    return _match_verdict(messages[1:], approver_id)


def _match_verdict(messages: list, approver_id: str) -> str:
    for msg in messages:
        if approver_id and msg.get("user") != approver_id:
            continue
        verdict = classify_reply(msg.get("text", ""))
        if verdict:
            return verdict
    return ""


def merge_candidates(thread_messages: list, channel_messages: list, thread_ts: str) -> list:
    """스레드 답글과, 스레드가 아니라 채널에 그냥 새 메시지로 올라온 답을 시간순으로 합친다.

    2026-09-23 첫 실사용 테스트에서 "이 스레드에 답글을 달아주세요"라고 안내했는데도
    사용자가 스레드가 아니라 채널에 바로 "발송"이라고 쳐서 승인을 놓쳤다. 슬랙 클라이언트가
    기본적으로 스레드 모드로 안 들어가는 경우가 흔해, 둘 다 본다.
    thread_messages[0]과 channel_messages 중 ts==thread_ts인 항목은 봇이 올린 원본이라 뺀다.
    """
    candidates = thread_messages[1:] + [
        m for m in channel_messages if m.get("ts") != thread_ts
    ]
    candidates.sort(key=lambda m: float(m.get("ts") or 0))
    return candidates


def request_slack_approval(message: str, timeout_min: int) -> bool:
    guide = (
        "*📦 커머스 브리핑 발송 승인*\n"
        "이 스레드에 `발송` 또는 `취소` 라고 답글을 달아주세요.\n"
        f"{timeout_min}분 안에 답이 없으면 자동 취소됩니다.\n\n"
        f"```\n{message}\n```"
    )
    posted = _slack_request("chat.postMessage", "POST", {
        "channel": SLACK_APPROVAL_CHANNEL,
        "text": guide,
    })
    thread_ts = posted["ts"]
    print(f"  [슬랙] 승인 요청을 올렸습니다. 답글을 기다립니다 (최대 {timeout_min}분)")

    deadline = time.time() + timeout_min * 60
    verdict = ""
    while time.time() < deadline:
        time.sleep(_SLACK_POLL_SEC)
        replies = _slack_request("conversations.replies", "GET", {
            "channel": SLACK_APPROVAL_CHANNEL,
            "ts": thread_ts,
            "limit": 50,
        })
        history = _slack_request("conversations.history", "GET", {
            "channel": SLACK_APPROVAL_CHANNEL,
            "oldest": thread_ts,
            "limit": 50,
        })
        candidates = merge_candidates(
            replies.get("messages", []), history.get("messages", []), thread_ts
        )
        verdict = _match_verdict(candidates, SLACK_APPROVER_USER_ID)
        if verdict:
            break

    notice = {"approve": "발송합니다.", "cancel": "취소했습니다."}.get(
        verdict, "시간이 지나 자동 취소했습니다."
    )
    try:
        _slack_request("chat.postMessage", "POST", {
            "channel": SLACK_APPROVAL_CHANNEL,
            "thread_ts": thread_ts,
            "text": notice,
        })
    except SlackApprovalError:
        pass  # 결과 통지 실패가 발송 자체를 막을 이유는 없다

    return verdict == "approve"


def request_approval(message: str, timeout_min: int) -> bool:
    """슬랙이 설정돼 있으면 슬랙으로, 아니면 PC 팝업으로 승인받는다.

    슬랙이 중간에 실패하면 팝업으로 내려온다 — 어차피 PC는 켜져 있어야
    발송이 되는 구조라, 팝업이 마지막 방어선으로 남는 편이 낫다.
    """
    if slack_configured():
        try:
            return request_slack_approval(message, timeout_min)
        except SlackApprovalError as e:
            print(f"  [슬랙] 승인 실패 ({e}) — PC 팝업으로 전환합니다.")
    return show_confirmation(message, timeout_min)


class KakaoWindowError(Exception):
    pass


def find_kakao_window(title: str):
    if not title:
        raise KakaoWindowError("KAKAO_CHATROOM_NAME이 설정되지 않았습니다.")
    matches = Desktop(backend="uia").windows(title=title)
    if len(matches) == 0:
        raise KakaoWindowError(f"'{title}' 이름의 채팅방 창을 찾지 못했습니다. 채팅방을 별도 창으로 열어두었는지 확인하세요.")
    if len(matches) > 1:
        raise KakaoWindowError(f"'{title}' 이름의 창이 {len(matches)}개 발견되어 어느 창인지 알 수 없습니다.")
    return matches[0]


def _set_clipboard(text: str) -> None:
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


# 빈 입력창을 읽으면 실제로는 빈 문자열이 아니라 카카오톡의 회색 안내문구가
# 그대로 읽히는 경우가 실제 테스트에서 확인됐다 ("메시지 입력"). 이걸 "아직
# 안 비었다"고 오판하면, 정상 전송된 메시지를 실패로 잘못 판정하게 된다.
_EMPTY_PLACEHOLDER_TEXTS = {"", "메시지 입력"}


def _is_effectively_empty(text: str) -> bool:
    return text.strip() in _EMPTY_PLACEHOLDER_TEXTS


def _normalize_newlines(text: str) -> str:
    """Windows RICHEDIT 컨트롤은 줄바꿈을 내부적으로 \\n이 아니라 \\r로
    저장한다 — 실제 테스트에서 여러 줄 메시지가 매번 검증 실패로 잡히는
    원인이었다. 비교 전에 양쪽을 같은 형태로 정규화한다."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _paste_matches(message: str, actual: str) -> bool:
    return bool(actual) and _normalize_newlines(actual.strip()) == _normalize_newlines(message.strip())


def _describe_mismatch(message: str, actual: str) -> str:
    """검증 실패 시 어디서부터 달라졌는지 로그에 남긴다. 2026-09-30에 "일치하지
    않음"만 남아 원인(붙여넣기가 덜 끝남 / 다른 창에 붙음 / 글자 변형)을
    구분할 수 없었다."""
    a = _normalize_newlines(message.strip())
    b = _normalize_newlines(actual.strip())
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return (
        f"원본 {len(a)}자 / 입력창 {len(b)}자, {i + 1}번째 글자부터 다름: "
        f"원본 {a[i:i + 20]!r} / 입력창 {b[i:i + 20]!r}"
    )


def _wait_for_paste(edit, message: str, timeout_sec: float = 2.0) -> str:
    """긴 메시지(링크 5개)는 Ctrl+V 후 0.3초 안에 다 들어오지 않을 수 있다.
    일치할 때까지 최대 timeout_sec 동안 200ms 간격으로 다시 읽는다."""
    actual = ""
    deadline = time.monotonic() + timeout_sec
    while True:
        actual = _read_edit_text(edit)
        if _paste_matches(message, actual) or time.monotonic() >= deadline:
            return actual
        time.sleep(0.2)


def _read_edit_text(edit) -> str:
    """RICHEDIT50W(Document 컨트롤)는 ValuePattern을 지원하지 않는 경우가 많다.
    get_value()가 없거나 실패하면 TextPattern(DocumentRange)으로 재시도한다.
    iface_text는 pywinauto의 lazy_property라 함수가 아니라 속성으로 접근해야 한다."""
    try:
        val = edit.get_value()
        if val:
            return val
    except Exception:
        pass
    try:
        return edit.iface_text.DocumentRange.GetText(-1)
    except Exception:
        return ""


def _select_all_and_delete(edit) -> None:
    """입력창 내용을 전체 선택 후 삭제한다.
    Ctrl+A 키 입력(^a)은 한글 IME와 타이밍이 겹치면 '전체 선택'이 아니라
    실제 'ㅁ' 글자가 입력되는 현상이 실제 테스트에서 발견됐다(물리 키보드에서
    'a' 키가 두벌식 자판의 'ㅁ'과 같은 위치). 키 입력 대신 TextPattern으로
    문서 범위를 직접 선택해 이 문제를 피한다."""
    edit.iface_text.DocumentRange.Select()
    edit.type_keys("{DELETE}", pause=0.05)


def _clear_edit(edit) -> bool:
    """실패 시 실제 채팅방 입력창에 붙여넣은 메시지가 그대로 남아
    누군가 Enter를 누르면 승인 없이 전송될 수 있으므로, 실패 경로에서는
    최선을 다해 입력창을 비운다. 실제로 비웠는지 여부를 반환해 호출부가
    사용자에게 정확한 상태를 알릴 수 있게 한다."""
    try:
        _select_all_and_delete(edit)
        return True
    except Exception:
        return False


def _clear_note(cleared: bool) -> str:
    return "(입력창을 비웠습니다)" if cleared else "(입력창을 비우지 못했습니다 — 실제 채팅방을 직접 확인하세요)"


def _paste_and_verify(window, message: str):
    """입력창에 메시지를 붙여넣고 원본과 같은지 확인한 뒤 입력창 컨트롤을 반환한다.
    Enter는 누르지 않는다 — 전송은 send_via_kakao()가, 시험(--test-paste)은
    확인 후 바로 비운다."""
    # 캘리브레이션 결과(2026-09-03, 실제 대상 오픈채팅방 창 대상 read-only 조사):
    # 메시지 입력창은 control_type="Edit"이 아니라 control_type="Document"이며
    # class_name="RICHEDIT50W", automation_id="1006"이다.
    # set_focus()는 최소화 복원까지 내부적으로 처리하며, 카카오톡 창처럼
    # UIA WindowPattern(최소화 여부 조회)을 지원하지 않는 창에 대해서도
    # NoPatternInterfaceError를 자체적으로 잡아 무시하도록 되어 있다
    # (pywinauto.controls.uiawrapper.UIAWrapper.set_focus 참고).
    # 직접 is_minimized()/restore()를 호출하면 이 보호 없이 그대로 예외가
    # 터지므로 (실제 테스트에서 확인됨) set_focus()에 맡긴다.
    window.set_focus()
    time.sleep(0.3)

    # find_kakao_window()가 반환하는 window는 WindowSpecification이 아니라
    # 원시 UIAWrapper라 child_window()가 없다 (실제 테스트에서 확인됨).
    # descendants()로 직접 찾는다 — 이 창에는 Document 컨트롤이 입력창 하나뿐이다.
    doc_matches = window.descendants(control_type="Document")
    if len(doc_matches) != 1:
        raise KakaoWindowError(
            f"메시지 입력창을 정확히 찾지 못했습니다 (Document 컨트롤 {len(doc_matches)}개 발견)."
        )
    edit = doc_matches[0]
    edit.click_input()
    _select_all_and_delete(edit)

    _set_clipboard(message)
    edit.type_keys("^v", pause=0.1)
    time.sleep(0.3)

    actual = _wait_for_paste(edit, message)
    if not _paste_matches(message, actual):
        cleared = _clear_edit(edit)
        raise KakaoWindowError(
            f"입력창 내용이 원본 메시지와 일치하지 않아 전송을 중단했습니다. {_clear_note(cleared)}\n"
            f"  {_describe_mismatch(message, actual)}"
        )
    return edit


def send_via_kakao(window, message: str) -> bool:
    edit = _paste_and_verify(window, message)
    edit.type_keys("{ENTER}")

    # 5개 URL이 섞인 긴 메시지는 카카오톡의 자동 링크 서식 처리가 늦게 끝날 수 있어
    # 고정 sleep 한 번이 아니라 최대 2초(200ms 간격)까지 입력창이 비는지 폴링한다.
    sent_confirmed = False
    for _ in range(10):
        time.sleep(0.2)
        if _is_effectively_empty(_read_edit_text(edit)):
            sent_confirmed = True
            break

    if not sent_confirmed:
        cleared = _clear_edit(edit)
        raise KakaoWindowError(
            "Enter 입력 후 2초가 지나도 입력창이 비지 않아 전송 여부를 확인할 수 없습니다. "
            f"실제로는 전송됐을 수 있으니 재시도하기 전에 채팅방을 직접 확인하세요. {_clear_note(cleared)}"
        )

    return True


def main():
    date_str = today_str()
    print(f"\n▶ 카톡 브리핑 발송 시작 [{date_str}]{'  [dry-run]' if DRY_RUN else ''}\n")

    if TEST_APPROVAL:
        print("승인 경로만 시험합니다. 실제 카톡 발송은 하지 않습니다.\n")
        ok = request_approval(f"(테스트) 커머스 브리핑 승인 확인 | {date_str}", KAKAO_APPROVAL_TIMEOUT_MIN)
        print(f"\n결과: {'승인됨' if ok else '취소 또는 시간 초과'}")
        return

    instance = acquire_single_instance()
    if instance is None:
        print("다른 카톡 봇이 이미 실행 중입니다. 중복 발송을 막기 위해 종료합니다.")
        return

    if already_sent(date_str):
        print("오늘 이미 발송했습니다. 종료합니다.")
        return

    if not git_pull():
        notify_failure(date_str, "git pull 실패")
        sys.exit(1)

    filepath = os.path.join(TRENDS_DIR, f"trend_{date_str}.txt")
    if not os.path.exists(filepath):
        print("오늘자 리포트가 아직 없습니다 (미발행일 수 있음). 종료합니다.")
        return

    with open(filepath, encoding="utf-8") as f:
        grouped = parse_trend_file(f.read())

    kr, gl = select_representative(grouped, kr_n=4, gl_n=1)
    if not should_send(kr, gl):
        print(f"기사 수가 부족합니다 (국내 {len(kr)}개 + 해외 {len(gl)}개). 종료합니다.")
        return

    message = build_message(date_str, kr, gl)
    print("\n" + "─" * 40 + f"\n{message}\n" + "─" * 40 + "\n")

    if DRY_RUN:
        print("[dry-run] 여기까지만 실행하고 종료합니다.")
        return

    if TEST_PASTE:
        print("붙여넣기 검증만 시험합니다. Enter는 누르지 않고 입력창을 비웁니다.\n")
        try:
            edit = _paste_and_verify(find_kakao_window(KAKAO_CHATROOM_NAME), message)
        except Exception as e:
            print(f"결과: 실패 — {e}")
            return
        print(f"결과: 일치 확인 {_clear_note(_clear_edit(edit))}")
        return

    # 승인은 다른 기기에서도 하므로, 잠겨 있으면 승인 요청 맨 위에 미리 알린다.
    approval_message = f"⚠️ {LOCKED_NOTICE}\n\n{message}" if is_screen_locked() else message
    approved = request_approval(approval_message, KAKAO_APPROVAL_TIMEOUT_MIN)
    if not approved:
        notify_failure(date_str, "승인 대기 시간 초과 또는 취소", message)
        return

    # 승인 대기(최대 30분) 사이에 다른 경로로 이미 나갔을 수 있다.
    if already_sent(date_str):
        print("승인 대기 중에 이미 발송됐습니다. 중복 발송하지 않고 종료합니다.")
        return

    # 승인 대기 중에 잠겼을 수 있다. 잠금 상태에서는 시도하지 않고 원인을 알린다.
    if is_screen_locked():
        notify_slack(f"⚠️ 발송 승인은 받았지만 보내지 못했습니다. {LOCKED_NOTICE}")
        notify_failure(date_str, f"화면 잠금 — {LOCKED_NOTICE}", message)
        return

    try:
        window = find_kakao_window(KAKAO_CHATROOM_NAME)
        send_via_kakao(window, message)
    except Exception as e:
        notify_slack(f"⚠️ 발송 승인은 받았지만 카톡 전송에 실패했습니다: {e}")
        notify_failure(date_str, f"전송 실패: {e}", message)
        return

    mark_sent(date_str)
    print(f"\n✓ 완료! → {KAKAO_CHATROOM_NAME}\n")


if __name__ == "__main__":
    main()
