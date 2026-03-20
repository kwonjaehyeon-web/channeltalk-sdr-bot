"""
DART 전자공시 수집기
공식 Open API 사용 → 법적 리스크 없음
API 발급: https://opendart.fss.or.kr
"""

import os
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


DART_BASE_URL = "https://opendart.fss.or.kr/api"


class DartCollector:

    def __init__(self):
        self.api_key = os.environ.get("DART_API_KEY")
        if not self.api_key:
            logger.warning("DART_API_KEY 미설정 — DART 수집 비활성화")

    def fetch(self, company_name: str) -> list[dict]:
        """기업명으로 DART 공시 목록 수집"""
        if not self.api_key:
            return []

        corp_code = self._get_corp_code(company_name)
        if not corp_code:
            logger.warning(f"[DART] {company_name} 기업 코드 없음")
            return []

        filings = self._get_filings(corp_code)
        return self._parse_filings(filings)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _get_corp_code(self, company_name: str) -> str | None:
        """기업명 → DART 고유 기업 코드 조회"""
        with httpx.Client(timeout=10) as client:
            res = client.get(
                f"{DART_BASE_URL}/company.json",
                params={"crtfc_key": self.api_key, "corp_name": company_name},
            )
            res.raise_for_status()
            data = res.json()

            if data.get("status") == "000" and data.get("list"):
                # 정확히 일치하는 기업명 우선
                for item in data["list"]:
                    if item["corp_name"] == company_name:
                        return item["corp_code"]
                return data["list"][0]["corp_code"]
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _get_filings(self, corp_code: str) -> list[dict]:
        """최근 2년 공시 목록 조회"""
        with httpx.Client(timeout=10) as client:
            res = client.get(
                f"{DART_BASE_URL}/list.json",
                params={
                    "crtfc_key": self.api_key,
                    "corp_code": corp_code,
                    "bgn_de": _two_years_ago(),
                    "page_count": 40,
                    "sort": "date",
                    "sort_mth": "desc",
                },
            )
            res.raise_for_status()
            data = res.json()
            return data.get("list", []) if data.get("status") == "000" else []

    def _parse_filings(self, filings: list[dict]) -> list[dict]:
        """공시 데이터 정규화 + 이벤트 분류"""
        results = []
        for f in filings:
            event_type = _classify_filing(f.get("report_nm", ""))
            results.append({
                "source": "dart",
                "date": f.get("rcept_dt"),
                "title": f.get("report_nm"),
                "event_type": event_type,   # investment | ma | executive | restructure | finance | other
                "corp_name": f.get("corp_name"),
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f.get('rcept_no')}",
            })
        return results


# ─── 유틸 ────────────────────────────────────────────────────────────────────

def _two_years_ago() -> str:
    from datetime import datetime, timedelta
    return (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")


def _classify_filing(title: str) -> str:
    """공시 제목 → 이벤트 유형 분류"""
    title = title.lower()
    if any(k in title for k in ["투자", "출자", "취득"]):
        return "investment"
    if any(k in title for k in ["합병", "분할", "양수", "양도", "인수"]):
        return "ma"
    if any(k in title for k in ["대표이사", "임원", "등기"]):
        return "executive"
    if any(k in title for k in ["조직", "사업부", "분사"]):
        return "restructure"
    if any(k in title for k in ["차입", "사채", "유상증자", "전환사채"]):
        return "finance"
    return "other"
