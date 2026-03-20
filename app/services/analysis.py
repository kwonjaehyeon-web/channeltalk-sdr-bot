"""
규칙 기반 분석 서비스 (LLM 미사용)
- ICP Fit: High / Medium / Low
- Company Type: Startup / Mid-market / Enterprise
- Pain Point 후보 추출 (산업군 + 재무 기반)
- 구매 신호 스코어 계산

LLM은 llm.py에서만 사용
"""

from loguru import logger

# ── 산업군별 기본 Pain Point 맵 ───────────────────────────────────────────────
INDUSTRY_PAIN_MAP = {
    "IT서비스":   ["개발 인력 확보 어려움", "기술 부채 누적", "보안/컴플라이언스 강화 압박"],
    "제조":       ["공급망 불안정", "생산 자동화 필요성 증가", "품질 관리 비용 상승"],
    "유통/물류":  ["재고 관리 비효율", "배송 지연 리스크", "라스트마일 비용 증가"],
    "금융":       ["레거시 시스템 전환", "규제 준수 비용", "디지털 채널 경쟁 심화"],
    "의료":       ["환자 데이터 관리 복잡성", "원격 진료 인프라 부족", "의료진 행정 부담"],
    "교육":       ["학습자 이탈률 관리", "콘텐츠 개인화 부재", "오프라인→온라인 전환"],
    "이커머스":   ["고객 리텐션 저하", "CS 문의량 급증", "데이터 기반 의사결정 부재"],
    "SaaS":       ["고객 온보딩 이탈", "MRR 성장 정체", "세일즈 파이프라인 가시성 부족"],
    "기타":       ["운영 효율화 필요", "데이터 사일로 문제", "디지털 전환 압박"],
}

# ── 스코어 가중치 ─────────────────────────────────────────────────────────────
SIGNAL_WEIGHTS = {
    "executive_change":     20,   # 임원 변경
    "investment":           20,   # 투자/자금 조달
    "ma":                   15,   # M&A
    "restructure":          15,   # 조직개편
    "revenue_growth":       10,   # 매출 성장 (추정)
    "large_enterprise":     10,   # 대기업
    "finance":              10,   # 자금 조달
}


class AnalysisService:

    def run(self, company_name: str, dart_data: dict) -> dict:
        """
        규칙 기반 분석 실행
        Returns: icp, company_type, pain_points(후보), score, signals
        """
        revenue        = dart_data.get("revenue")           # 억원, None 가능
        employee_count = dart_data.get("employee_count")    # 명, None 가능
        filings        = dart_data.get("filings", [])
        has_dart       = dart_data.get("source") == "dart"

        company_type = self._classify_company_type(revenue, employee_count)
        icp_fit      = self._classify_icp(company_type, revenue)
        industry     = self._infer_industry(company_name, filings)
        pain_candidates = self._get_pain_candidates(industry, revenue, filings)
        signals      = self._detect_signals(filings, company_type)
        score        = self._calculate_score(signals)

        return {
            "company_type":     company_type,
            "icp_fit":          icp_fit,
            "industry":         industry,
            "revenue_tier":     _format_revenue(revenue),
            "saas_readiness":   _saas_readiness(company_type, industry),
            "pain_candidates":  pain_candidates,
            "signals":          signals,
            "score":            score,
            "has_dart_data":    has_dart,
            "key_filings":      [f for f in filings if f["event_type"] != "other"][:5],
        }

    # ── 분류 로직 ────────────────────────────────────────────────────────────

    def _classify_company_type(
        self, revenue: int | None, employees: int | None
    ) -> str:
        """매출(억원) + 임직원수 기반 기업 규모 분류"""
        if revenue is not None:
            if revenue >= 1000:
                return "Enterprise"
            if revenue >= 100:
                return "Mid-market"
            return "Startup"

        if employees is not None:
            if employees >= 1000:
                return "Enterprise"
            if employees >= 100:
                return "Mid-market"
            return "Startup"

        return "Mid-market"   # 데이터 없으면 Mid-market으로 보수적 추정

    def _classify_icp(self, company_type: str, revenue: int | None) -> str:
        """ICP Fit 판정"""
        if company_type == "Enterprise":
            return "High"
        if company_type == "Mid-market":
            return "High" if (revenue and revenue >= 300) else "Medium"
        return "Low"

    def _infer_industry(self, company_name: str, filings: list) -> str:
        """기업명 키워드로 산업군 추정 (DART 데이터 없을 때 fallback)"""
        name = company_name.lower()
        if any(k in name for k in ["it", "시스템", "솔루션", "테크", "소프트", "클라우드"]):
            return "IT서비스"
        if any(k in name for k in ["제조", "공업", "산업", "화학", "철강"]):
            return "제조"
        if any(k in name for k in ["물류", "배송", "유통", "마트", "쇼핑"]):
            return "유통/물류"
        if any(k in name for k in ["은행", "증권", "보험", "금융", "캐피탈"]):
            return "금융"
        if any(k in name for k in ["병원", "의료", "헬스", "제약", "바이오"]):
            return "의료"
        if any(k in name for k in ["교육", "학원", "에듀"]):
            return "교육"
        return "기타"

    def _get_pain_candidates(
        self, industry: str, revenue: int | None, filings: list
    ) -> list[dict]:
        """산업군 기반 Pain Point 후보 반환 (LLM이 다음 단계에서 표현 다듬음)"""
        base_pains = INDUSTRY_PAIN_MAP.get(industry, INDUSTRY_PAIN_MAP["기타"])
        result = []

        for pain in base_pains:
            result.append({
                "pain":          pain,
                "evidence":      f"{industry} 업종 공통 과제",
                "solution_hint": _pain_to_solution(pain),
            })

        # 재무 기반 추가 Pain
        if revenue is not None and revenue < 500:
            result.append({
                "pain":          "제한된 IT 예산 내 최대 효율 필요",
                "evidence":      f"추정 매출 {revenue}억원 규모",
                "solution_hint": "저비용 SaaS 구독 모델",
            })

        # 공시 기반 추가 Pain
        event_types = [f["event_type"] for f in filings]
        if "executive" in event_types:
            result.append({
                "pain":          "경영진 교체로 인한 전략 방향 재정립 필요",
                "evidence":      "최근 임원 변경 공시 감지",
                "solution_hint": "전략 컨설팅 / 데이터 기반 의사결정 툴",
            })
        if "ma" in event_types:
            result.append({
                "pain":          "M&A 후 시스템 통합 및 조직 정렬 필요",
                "evidence":      "최근 M&A 관련 공시 감지",
                "solution_hint": "ERP / 통합 관리 플랫폼",
            })

        return result[:4]   # 최대 4개

    def _detect_signals(self, filings: list, company_type: str) -> list[str]:
        detected = []
        event_types = {f["event_type"] for f in filings}

        if "executive" in event_types:
            detected.append("executive_change")
        if "investment" in event_types:
            detected.append("investment")
        if "ma" in event_types:
            detected.append("ma")
        if "restructure" in event_types:
            detected.append("restructure")
        if "finance" in event_types:
            detected.append("finance")
        if company_type == "Enterprise":
            detected.append("large_enterprise")

        return detected

    def _calculate_score(self, signals: list[str]) -> int:
        total = sum(SIGNAL_WEIGHTS.get(s, 0) for s in signals)
        return min(total, 100)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _format_revenue(revenue: int | None) -> str:
    if revenue is None:
        return "미확인 (비상장 또는 데이터 없음)"
    if revenue >= 1_0000:
        return f"{revenue // 1_0000}조원대"
    return f"{revenue}억원대"


def _saas_readiness(company_type: str, industry: str) -> str:
    if company_type == "Enterprise":
        return "High — 대규모 도입 예산 존재, 구매 프로세스 복잡"
    if company_type == "Mid-market":
        return "High — 빠른 의사결정, PLG 또는 영업 주도 모두 유효"
    return "Medium — 예산 제한적, 무료 플랜→유료 전환 전략 유효"


def _pain_to_solution(pain: str) -> str:
    mapping = {
        "인력":       "HR Tech / 채용 자동화",
        "보안":       "보안 SaaS (SIEM, IAM)",
        "자동화":     "RPA / 워크플로우 자동화",
        "데이터":     "BI / 데이터 분석 플랫폼",
        "고객":       "CRM / CS툴",
        "비용":       "비용 절감형 SaaS",
        "관리":       "ERP / 통합 관리 플랫폼",
        "전환":       "디지털 전환 컨설팅 / 클라우드",
    }
    for keyword, solution in mapping.items():
        if keyword in pain:
            return solution
    return "업무 생산성 SaaS"
