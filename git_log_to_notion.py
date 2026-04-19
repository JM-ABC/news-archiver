"""
git post-commit 훅에서 호출되는 스크립트.
커밋 정보(해시·메시지·변경 파일·diff 통계·실제 코드 변경)를 Notion 페이지에 기록한다.

필요 환경변수 (.env):
  NOTION_API_KEY           — Notion Integration 토큰
  NOTION_CHANGELOG_PAGE_ID — 변경 로그를 쌓을 Notion 페이지 ID
"""

import os
import subprocess
import sys
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY           = os.getenv("NOTION_API_KEY")
NOTION_CHANGELOG_PAGE_ID = os.getenv("NOTION_CHANGELOG_PAGE_ID")


def _git(*args) -> str:
    return subprocess.check_output(["git"] + list(args), text=True, encoding="utf-8").strip()


def get_commit_info() -> dict:
    hash_short = _git("rev-parse", "--short", "HEAD")
    message    = _git("log", "-1", "--pretty=%B").strip()
    author     = _git("log", "-1", "--pretty=%an")
    date_str   = _git("log", "-1", "--pretty=%ai")          # 2026-04-15 09:00:00 +0900

    # 변경 파일 목록: "M\tpath/to/file" 형식
    files_raw = _git("diff-tree", "--no-commit-id", "-r", "--name-status", "HEAD")
    # diff 통계 마지막 줄: "3 files changed, 42 insertions(+), 7 deletions(-)"
    stat_lines = _git("diff-tree", "--no-commit-id", "-r", "--stat", "HEAD").splitlines()
    stat_summary = next((l for l in reversed(stat_lines) if "changed" in l), "")
    # 실제 코드 변경 내용 (diff 형식)
    diff_raw = _git("diff-tree", "-p", "--no-color", "HEAD")

    return {
        "hash":    hash_short,
        "message": message,
        "author":  author,
        "date":    date_str,
        "files":   files_raw,
        "stat":    stat_summary.strip(),
        "diff":    diff_raw,
    }


STATUS_ICON = {"A": "➕", "M": "✏️", "D": "🗑️", "R": "🔀"}


def build_blocks(info: dict) -> list[dict]:
    title = f"[{info['hash']}] {info['message'][:180]}"

    blocks = [
        # 제목
        {
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": title}}]},
        },
        # 날짜 · 작성자
        {
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"📅 {info['date']}   👤 {info['author']}"},
                 "annotations": {"color": "gray"}},
            ]},
        },
    ]

    # 변경 파일 목록
    for line in info["files"].splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        status = parts[0][0] if parts else "M"
        path   = parts[1] if len(parts) > 1 else line
        icon   = STATUS_ICON.get(status, "•")
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"  {icon} {path}"},
                 "annotations": {"code": False}},
            ]},
        })

    # diff 통계
    if info["stat"]:
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"📊 {info['stat']}"},
                 "annotations": {"color": "gray"}},
            ]},
        })

    # 실제 코드 변경 내용 (diff) — Notion 코드블록 최대 2000자씩 분할
    CHUNK = 1900
    diff = info.get("diff", "")
    if diff:
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": "코드 변경 내용"},
                 "annotations": {"bold": True}},
            ]},
        })
        for i in range(0, len(diff), CHUNK):
            blocks.append({
                "object": "block", "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": diff[i:i + CHUNK]}}],
                    "language": "diff",
                },
            })

    # 구분선
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    return blocks


def main():
    if not NOTION_API_KEY:
        print("[git_log_to_notion] NOTION_API_KEY 없음 — 건너뜁니다.")
        sys.exit(0)
    if not NOTION_CHANGELOG_PAGE_ID:
        print("[git_log_to_notion] NOTION_CHANGELOG_PAGE_ID 없음 — 건너뜁니다.")
        sys.exit(0)

    try:
        info   = get_commit_info()
        blocks = build_blocks(info)
        notion = Client(auth=NOTION_API_KEY)
        notion.blocks.children.append(NOTION_CHANGELOG_PAGE_ID, children=blocks)
        print(f"[git_log_to_notion] Notion 기록 완료 → {info['hash']} {info['message'][:60]}")
    except Exception as e:
        # 훅 실패가 커밋을 막으면 안 되므로 에러만 출력하고 종료
        print(f"[git_log_to_notion] 오류 (커밋은 정상 완료): {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
