"""
신호 감지 + 스코어 계산 엔진

스코어 기준 (0-100):
  고신뢰 신호: +20~30
  중간 신뢰:   +10~15
  약한 신호:   +5
  최대 100 cap
"""

from collections import Counter
from loguru import logger


# ─── 신호별 가중치 ────────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    # 고신뢰
    "dx_org_created": 30,       # DX본부/디지털전환TF 신설 채용
    "cto_cdo_new_hire": 25,     # CTO/CDO 신규 채용
    "it_investment_100b": 25,   # IT 인프라 100억 이상 투자 공시
    "spinoff_or_split": 20,     # 기업 분할/자회사 설립
    "ceo_change": 20,           # 대표이사 교체 (90일 이내)

    # 중간 신뢰
    "cloud_hiring_surge": 15,   # AWS/Azure 관련 채용 급증
    "tech_hiring_surge_30": 12, # IT 직군 채용 전월 대비 30% 증가
    "tech_executive_import": 10, # 스타트업/테크 출신 임원 영입

    # 약한 신호
    "it_conference_sponsor": 5,
    "website_renewal": 5,
}


class SignalDetector:

    def detect(self, dart_data: list, job_data: list, news_data: list) -> dict:
        """수집된 데이터에서 영업 신호 감지"""
        signals = {
            "top_signals": [],
            "job_summary": {},
            "dart_events": [],
            "raw_counts": {},
        }

        signals["job_summary"] = self._analyze_jobs(job_data)
        signals["dart_events"] = self._analyze_dart(dart_data)
        signals["top_signals"] = self._extract_top_signals(
            signals["job_summary"], signals["dart_events"], news_data
        )

        return signals

    def score(self, signals: dict) -> int:
        """신호 목록 → 스코어 (0-100)"""
        total = 0
        for signal in signals.get("top_signals", []):
            weight = SIGNAL_WEIGHTS.get(signal["type"], 0)
            total += weight

        return min(total, 100)

    def check_delta(self, company_name: str) -> tuple[bool, str]:
        """
        워치리스트 기업 변화 감지 (배치용)
        TODO: DB에 저장된 이전 스코어와 비교
        """
        from src.db.session import get_cached_report
        cached = get_cached_report(company_name, max_age_hours=168)  # 7일
        if not cached:
            return False, ""
        # 간단한 버전: 캐시가 오래됐으면 재분석 권고
        return False, ""

    # ─── 내부 분석 ──────────────────────────────────────────────────────────

    def _analyze_jobs(self, job_data: list) -> dict:
        if not job_data:
            return {}

        categories = Counter(j["category"] for j in job_data)
        management_count = sum(1 for j in job_data if j.get("is_management"))
        total = len(job_data)

        return {
            "total": total,
            "categories": dict(categories),
            "management_count": management_count,
            "tech_ratio": round(
                (categories.get("tech", 0) + categories.get("dx", 0)) / max(total, 1), 2
            ),
        }

    def _analyze_dart(self, dart_data: list) -> list[dict]:
        important = []
        for filing in dart_data:
            event_type = filing.get("event_type")
            if event_type in ("investment", "ma", "executive", "restructure", "finance"):
                important.append({
                    "type": event_type,
                    "title": filing.get("title"),
                    "date": filing.get("date"),
                    "url": filing.get("url"),
                })
        return important[:5]  # 상위 5개만

    def _extract_top_signals(self, job_summary: dict, dart_events: list, news_data: list) -> list[dict]:
        signals = []

        # DX/디지털전환 채용 비중 높음
        if job_summary.get("tech_ratio", 0) >= 0.4:
            signals.append({
                "type": "tech_hiring_surge_30",
                "description": f"IT/DX 직군 채용 비중 {int(job_summary['tech_ratio'] * 100)}% — 디지털 전환 진행 중",
                "confidence": "high",
            })

        # 관리자급 채용
        if job_summary.get("management_count", 0) >= 2:
            signals.append({
                "type": "cto_cdo_new_hire",
                "description": f"관리자급(팀장 이상) 채용 {job_summary['management_count']}건 — 의사결정권자 변화",
                "confidence": "high",
            })

        # DART 투자 공시
        for event in dart_events:
            if event["type"] == "investment":
                signals.append({
                    "type": "it_investment_100b",
                    "description": f"공시: {event['title']} ({event['date']})",
                    "confidence": "high",
                    "source_url": event.get("url"),
                })
            elif event["type"] == "executive":
                signals.append({
                    "type": "ceo_change",
                    "description": f"임원 변경 공시: {event['title']} ({event['date']})",
                    "confidence": "medium",
                })

        # 뉴스에서 DX/클라우드 키워드
        dx_news = [
            n for n in news_data
            if any(k in (n.get("title", "") + n.get("snippet", ""))
                   for k in ["디지털전환", "클라우드", "AI", "DX", "스마트팩토리"])
        ]
        if dx_news:
            signals.append({
                "type": "cloud_hiring_surge",
                "description": f"최근 DX/클라우드 관련 뉴스 {len(dx_news)}건 감지",
                "confidence": "medium",
            })

        return signals[:6]  # 상위 6개 신호만 반환
