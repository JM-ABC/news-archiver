#!/usr/bin/env bash
# 최초 1회 실행 — 의존성 설치 + .env 파일 생성

set -e

echo "=== 뉴스 아카이버 설치 ==="

# 1. 의존성 설치
pip install -r requirements.txt

# 2. .env 파일 생성
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "✓ .env 파일 생성 완료"
  echo "  → .env 파일을 열어 API 키를 입력하세요:"
  echo "     ANTHROPIC_API_KEY=sk-ant-..."
  echo "     NOTION_API_KEY=secret_..."
  echo "     NOTION_DATABASE_ID=... (또는 NOTION_PAGE_ID=...)"
else
  echo "✓ .env 파일 이미 존재 (건너뜀)"
fi

# 3. 저장 폴더 생성
mkdir -p ~/trends
echo "✓ ~/trends 폴더 준비 완료"

echo ""
echo "설치 완료! 다음 명령으로 실행하세요:"
echo "  python news_archiver.py"
