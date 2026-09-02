"""
커머스 브리핑 카톡 자동 발송 봇
- trends/trend_YYYY-MM-DD.txt에서 대표 5개(국내 4 + 해외 1) 추출
- 발송 전 사람 승인 팝업 → 승인 시에만 카카오톡 PC 앱으로 전송
- 실패/취소 시 이메일로 알림
"""

import os
import re
import sys
import datetime

from dotenv import load_dotenv

from news_archiver import REGION_KR, REGION_GL

load_dotenv()

TRENDS_DIR = os.getenv("TRENDS_DIR", "./trends")
KAKAO_CHATROOM_NAME = os.getenv("KAKAO_CHATROOM_NAME", "")
KAKAO_APPROVAL_TIMEOUT_MIN = int(os.getenv("KAKAO_APPROVAL_TIMEOUT_MIN", "30"))
DRY_RUN = "--dry-run" in sys.argv

KST = datetime.timezone(datetime.timedelta(hours=9))


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
