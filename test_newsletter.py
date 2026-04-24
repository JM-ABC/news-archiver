"""뉴스레터 디자인 미리보기 — 샘플 데이터로 test_newsletter.html 생성"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

# news_archiver의 _build_html, 상수만 가져오기
from news_archiver import _build_html, REGION_KR, REGION_GL

DATE_STR = "2026-03-21"

SAMPLE_INSIGHTS = [
    "쿠팡·네이버, 지방 물류 확충으로 익일배송 커버리지 전쟁 본격화\n수도권 중심이던 빠른배송 인프라가 충청·경상권으로 빠르게 확장되고 있습니다. 지방 소비자 락인 경쟁이 플랫폼 성장의 핵심 변수로 부상하고 있습니다.",
    "메타·구글 AI 광고 자동화, 국내 이커머스 ROAS 평균 30%↑ 효과 입증\nAdvantage+·PMax 도입 사례가 누적되며 소규모 셀러의 광고 효율화가 현실화되고 있습니다.",
    "라이브커머스 성숙기 진입 — 단순 할인 방송에서 브랜드 IP 강화 수단으로 전환\n카카오·네이버 라이브 채널의 재구매율 지표가 개선되며 커머스 채널로서의 지속성이 확인되고 있습니다.",
]

SAMPLE_ARTICLES = [
    {
        "region": REGION_KR,
        "subcategory": "주요 플랫폼",
        "title_ko": "쿠팡, 대구·경북 물류센터 2곳 추가 — 익일배송권 전국 95%로 확대",
        "source": "KR-쿠팡",
        "summary": "- 지방 소비자 락인 전략의 일환으로 풀필먼트 인프라를 집중 확충\n- 네이버·11번가와의 지역 배송 경쟁이 본격화될 전망입니다\n- PB 브랜드 매출 비중이 처음으로 20%를 넘어섰다",
        "insight": "지방 물류 선점이 중장기 시장점유율을 결정하는 핵심 변수로 부상하고 있습니다.",
        "url": "https://example.com/article/1",
    },
    {
        "region": REGION_KR,
        "subcategory": "주요 플랫폼",
        "title_ko": "네이버 스마트스토어, 'AI 상품 설명 자동 생성' 전면 도입 — 셀러 반응 긍정적",
        "source": "KR-네이버쇼핑",
        "summary": "- 키워드 입력만으로 SEO 최적화 상품 설명을 자동 작성하는 기능 베타 종료 후 전면 오픈\n- 실제 오류 수정 및 편집 시간이 18% 감소한 것으로 보고됩니다",
        "insight": "AI 상품 등록 도구의 보편화가 중소 셀러의 플랫폼 의존도를 높이는 방향으로 작용하고 있습니다.",
        "url": "https://example.com/article/2",
    },
    {
        "region": REGION_KR,
        "subcategory": "배송/물류",
        "title_ko": "배달의민족, 'B마트 퀵커머스' SKU 3만 개로 확대 — 편의점·마트 대체 가속",
        "source": "KR-배민",
        "summary": "- 신선식품·가공식품 중심으로 취급 품목을 늘리며 즉시배송 수요를 흡수\n- 쿠팡이츠·마트와의 전면 경쟁 구도가 뚜렷해졌습니다",
        "insight": "즉시배송 카테고리 확장이 오프라인 편의점 트래픽을 잠식하는 속도가 빨라지고 있습니다.",
        "url": "https://example.com/article/3",
    },
    {
        "region": REGION_KR,
        "subcategory": "마케팅",
        "title_ko": "메타 Advantage+, 국내 광고주 ROAS 평균 34% 향상 — 소규모 셀러 효과 증명",
        "source": "KR-이커머스",
        "summary": "- AI 자동화 캠페인이 수동 세팅 대비 CPA를 낮추는 사례가 증가\n- 단, 크리에이티브 품질이 성과의 70%를 결정한다는 점에서 기획 역량이 더욱 중요해지고 있습니다",
        "insight": "광고 자동화가 확산될수록 소재 제작 역량이 마케터의 핵심 경쟁력으로 부각됩니다.",
        "url": "https://example.com/article/4",
    },
    {
        "region": REGION_KR,
        "subcategory": "마케팅",
        "title_ko": "구글 AI Overview, 국내 커머스 검색 노출 영향 본격화 — SEO 전략 재편 필요",
        "source": "KR-소비트렌드",
        "summary": "- AI 요약 답변이 상단을 점령하면서 중간 클릭률이 최대 30% 감소한 사례 보고\n- 브랜드 직접 유입 강화와 리뷰 콘텐츠 최적화가 대안으로 분석되고 있습니다",
        "insight": "검색 트래픽 구조 변화에 대비한 브랜드 채널 다변화 전략이 시급합니다.",
        "url": "https://example.com/article/5",
    },
    {
        "region": REGION_KR,
        "subcategory": "유한킴벌리 경쟁사",
        "title_ko": "P&G 한국법인, 프리미엄 기저귀 라인 리뉴얼 — 쿠팡 PB와 직접 경쟁 구도",
        "source": "KR-유한킴벌리",
        "summary": "- 팸퍼스 프리미엄 라인 가격을 동결하며 가성비 PB 제품과의 차별화 강조\n- 온라인 정기구독 채널을 강화해 쿠팡 로켓배송 의존도를 줄이는 전략을 병행하고 있습니다",
        "insight": "PB 브랜드와의 가격 경쟁 심화 속에서 프리미엄 포지셔닝 강화가 브랜드사의 핵심 과제로 부상하고 있습니다.",
        "url": "https://example.com/article/6",
    },
    {
        "region": REGION_GL,
        "subcategory": "플랫폼",
        "title_ko": "아마존, 광고 사업부 분기 매출 60억 달러 돌파 — AWS 이어 핵심 수익원 안착",
        "source": "GL-글로벌",
        "summary": "- 스폰서드 상품 광고와 DSP 확대로 리테일 미디어 수익이 본격화됩니다\n- 셀러 광고 의존도가 높아지며 플랫폼 수수료 협상력도 강화되고 있습니다",
        "insight": "리테일 미디어가 이커머스 플랫폼의 제2 수익 엔진으로 완전히 자리잡고 있습니다.",
        "url": "https://example.com/article/7",
    },
    {
        "region": REGION_GL,
        "subcategory": "플랫폼",
        "title_ko": "Shopify, AI 에이전트 기반 '스토어 자동화' 기능 베타 출시",
        "source": "GL-글로벌",
        "summary": "- 상품 등록·가격 조정·CS 응대를 AI가 처리하는 자율 에이전트 기능 공개\n- 소규모 셀러의 운영 비용을 절감하는 효과가 기대되고 있습니다",
        "insight": "AI 에이전트 상용화로 1인 셀러의 운영 가능 SKU 범위가 대폭 확대될 것으로 예상됩니다.",
        "url": "https://example.com/article/8",
    },
    {
        "region": REGION_GL,
        "subcategory": "마케팅",
        "title_ko": "틱톡샵, 동남아 연간 GMV 40억 달러 돌파 — 한국 출시 일정 미정",
        "source": "GL-글로벌",
        "summary": "- 숏폼 연동 구매 전환 효과가 입증되며 한국 진출 압박도 높아지고 있습니다\n- 라이브 종료 후 48시간 내 VOD 재구매가 전체의 38%를 차지했습니다",
        "insight": "틱톡 커머스 모델의 성공이 국내 숏폼 플랫폼의 커머스 기능 강화를 앞당기고 있습니다.",
        "url": "https://example.com/article/9",
    },
]

if __name__ == "__main__":
    html = _build_html(SAMPLE_ARTICLES, DATE_STR, SAMPLE_INSIGHTS)
    output_path = "test_newsletter.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 미리보기 생성 완료: {output_path}")
    print("   브라우저에서 해당 파일을 열어 확인하세요.")
