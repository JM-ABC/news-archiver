"""
커머스 브리핑 카톡 자동 발송 봇
- trends/trend_YYYY-MM-DD.txt에서 대표 5개(국내 4 + 해외 1) 추출
- 발송 전 사람 승인 팝업 → 승인 시에만 카카오톡 PC 앱으로 전송
- 실패/취소 시 이메일로 알림
"""

import os
import re
import sys
import time
import datetime
import subprocess
import tkinter as tk

import resend
import win32clipboard
from dotenv import load_dotenv
from pywinauto import Desktop

from news_archiver import REGION_KR, REGION_GL

load_dotenv()

TRENDS_DIR = os.getenv("TRENDS_DIR", "./trends")
KAKAO_CHATROOM_NAME = os.getenv("KAKAO_CHATROOM_NAME", "")
KAKAO_APPROVAL_TIMEOUT_MIN = int(os.getenv("KAKAO_APPROVAL_TIMEOUT_MIN", "30"))
DRY_RUN = "--dry-run" in sys.argv

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


def mark_sent(date_str: str) -> None:
    os.makedirs(TRENDS_DIR, exist_ok=True)
    with open(_marker_path(date_str), "w", encoding="utf-8") as f:
        f.write(datetime.datetime.now(KST).isoformat())


_CIRCLE_RE = re.compile(r"^[①-⑳㉑-㉚]\s+(.+)$")


def parse_trend_file(text: str) -> dict:
    """trend_YYYY-MM-DD.txt 본문을 리전별 기사 목록으로 파싱한다.

    각 기사는 {"title", "insight", "summary", "url"} 딕셔너리.
    insight는 👉 시사점 문장, summary는 첫 요약 불렛(insight가 없을 때의 대체용).
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
            current = {"title": m.group(1).strip(), "insight": "", "summary": "", "url": ""}
            current_region = region
            continue

        if current is None:
            continue

        if line.startswith("👉"):
            current["insight"] = line.split("👉", 1)[1].strip()
        elif line.startswith("- ") and not current["summary"]:
            current["summary"] = line[2:].strip()
        elif line.startswith("원문:"):
            current["url"] = line.split("원문:", 1)[1].strip()
            grouped[current_region].append(current)
            current = None

    return grouped


def select_representative(grouped: dict, kr_n: int = 4, gl_n: int = 1):
    kr = grouped.get(REGION_KR, [])[:kr_n]
    gl = grouped.get(REGION_GL, [])[:gl_n]
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
    root.attributes("-topmost", True)

    tk.Label(root, text="아래 메시지를 오픈채팅방에 발송할까요?", font=("맑은 고딕", 11, "bold")).pack(pady=(12, 4))

    text_widget = tk.Text(root, wrap="word", font=("맑은 고딕", 10))
    text_widget.insert("1.0", message)
    text_widget.config(state="disabled")
    text_widget.pack(fill="both", expand=True, padx=12, pady=8)

    countdown_label = tk.Label(root, text="", fg="gray")
    countdown_label.pack()

    remaining = {"seconds": timeout_min * 60}

    def tick():
        if remaining["seconds"] <= 0:
            on_cancel()
            return
        mins, secs = divmod(remaining["seconds"], 60)
        countdown_label.config(text=f"{mins}분 {secs}초 안에 응답이 없으면 자동 취소됩니다.")
        remaining["seconds"] -= 1
        root.after(1000, tick)

    def on_approve():
        result["approved"] = True
        root.destroy()

    def on_cancel():
        result["approved"] = False
        root.destroy()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=12)
    tk.Button(button_frame, text="발송", width=12, bg="#111111", fg="white", command=on_approve).pack(side="left", padx=8)
    tk.Button(button_frame, text="취소", width=12, command=on_cancel).pack(side="left", padx=8)

    root.after(1000, tick)
    root.mainloop()
    return result["approved"]


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


def send_via_kakao(window, message: str) -> bool:
    window.set_focus()
    time.sleep(0.3)

    # NOTE: 실제 카카오톡 창에서 입력창 컨트롤을 찾는 부분은 캘리브레이션이 필요하다.
    # pywinauto의 print_control_identifiers()로 실제 컨트롤 이름을 확인한 뒤 아래 selector를 맞춘다.
    edit = window.child_window(control_type="Edit")
    edit.click_input()
    edit.type_keys("^a{DELETE}", pause=0.05)

    _set_clipboard(message)
    edit.type_keys("^v", pause=0.1)
    time.sleep(0.3)

    actual = edit.get_value() if hasattr(edit, "get_value") else edit.window_text()
    if actual.strip() != message.strip():
        raise KakaoWindowError("입력창 내용이 원본 메시지와 일치하지 않아 전송을 중단했습니다.")

    edit.type_keys("{ENTER}")
    time.sleep(0.3)
    return True


def main():
    date_str = today_str()
    print(f"\n▶ 카톡 브리핑 발송 시작 [{date_str}]{'  [dry-run]' if DRY_RUN else ''}\n")

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

    approved = show_confirmation(message, KAKAO_APPROVAL_TIMEOUT_MIN)
    if not approved:
        notify_failure(date_str, "승인 대기 시간 초과 또는 취소", message)
        return

    try:
        window = find_kakao_window(KAKAO_CHATROOM_NAME)
        send_via_kakao(window, message)
    except Exception as e:
        notify_failure(date_str, f"전송 실패: {e}", message)
        return

    mark_sent(date_str)
    print(f"\n✓ 완료! → {KAKAO_CHATROOM_NAME}\n")


if __name__ == "__main__":
    main()
