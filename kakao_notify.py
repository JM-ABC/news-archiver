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


# news_archiver.py의 _CIRCLE 리스트(①~㉚, 30개)와 짝을 맞춘 패턴이다.
# KR_MAX + GL_MAX가 30을 넘으면 news_archiver.circle_num()이 "(31)" 같은 일반 텍스트로
# 넘어가므로, 그 경우 이 정규식이 매칭하지 못해 해당 기사가 조용히 파싱에서 누락된다.
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


def _clear_edit(edit) -> bool:
    """실패 시 실제 채팅방 입력창에 붙여넣은 메시지가 그대로 남아
    누군가 Enter를 누르면 승인 없이 전송될 수 있으므로, 실패 경로에서는
    최선을 다해 입력창을 비운다. 실제로 비웠는지 여부를 반환해 호출부가
    사용자에게 정확한 상태를 알릴 수 있게 한다."""
    try:
        edit.type_keys("^a{DELETE}", pause=0.05)
        return True
    except Exception:
        return False


def _clear_note(cleared: bool) -> str:
    return "(입력창을 비웠습니다)" if cleared else "(입력창을 비우지 못했습니다 — 실제 채팅방을 직접 확인하세요)"


def send_via_kakao(window, message: str) -> bool:
    # 캘리브레이션 결과(2026-09-03, 실제 대상 오픈채팅방 창 대상 read-only 조사):
    # 메시지 입력창은 control_type="Edit"이 아니라 control_type="Document"이며
    # class_name="RICHEDIT50W", automation_id="1006"이다.
    if window.is_minimized():
        window.restore()
    window.set_focus()
    time.sleep(0.3)

    edit = window.child_window(auto_id="1006", control_type="Document")
    edit.click_input()
    edit.type_keys("^a{DELETE}", pause=0.05)

    _set_clipboard(message)
    edit.type_keys("^v", pause=0.1)
    time.sleep(0.3)

    actual = _read_edit_text(edit)
    if not actual or actual.strip() != message.strip():
        cleared = _clear_edit(edit)
        raise KakaoWindowError(
            f"입력창 내용이 원본 메시지와 일치하지 않아 전송을 중단했습니다. {_clear_note(cleared)}"
        )

    edit.type_keys("{ENTER}")

    # 5개 URL이 섞인 긴 메시지는 카카오톡의 자동 링크 서식 처리가 늦게 끝날 수 있어
    # 고정 sleep 한 번이 아니라 최대 2초(200ms 간격)까지 입력창이 비는지 폴링한다.
    sent_confirmed = False
    for _ in range(10):
        time.sleep(0.2)
        if not _read_edit_text(edit).strip():
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
