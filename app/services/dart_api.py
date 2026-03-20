"""
DART 전자공시 API 서비스
- 기업 코드 조회
- 최근 공시 이벤트 수집
- 재무 정보 (매출, 임직원수) 수집
공식 API: https://opendart.fss.or.kr
"""

import os
from datetime import datetime, timedelta
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DART_BASE = "https://opendart.fss.or.kr/api"

# 공시 이벤트 분류 키워드
EVENT_KEYWORDS = {
    "investment": ["투자", "출자", "취득"],
    "ma":         ["합병", "분할", "양수", "양도", "인수"],
    "executive":  ["대표이사", "임원", "등기"],
    "restructure":["조직", "사업부", "분사"],
    "finance":    ["차입", "사채", "유상증자", "전환사채"],
}


class DartAPIError(Exception):
    pass


class DartService:

    def __init__(self):
        self.api_key = os.environ.get("DART_API_KEY")
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.warning("DART_API_KEY 없음 — DART 수집 비활성화")

    # ── 퍼블릭 인터페이스 ────────────────────────────────────────────────────

    def fetch(self, company_name: str) -> dict:
        """
        기업명 → DART 데이터 반환
        Returns:
          corp_code, corp_name, filings(list), employee_count, revenue
        """
        if not self.enabled:
            return _empty_result(company_name)

        corp_code = self._get_corp_code(company_name)
        if not corp_code:
            logger.info(f"[DART] {company_name} 기업코드 없음 (비상장 가능성)")
            return _empty_result(company_name)

        filings   = self._get_filings(corp_code)
        financials = self._get_financials(corp_code)

        return {
            "corp_code":      corp_code,
            "corp_name":      company_name,
            "filings":        filings,
            "employee_count": financials.get("employee_count"),
            "revenue":        financials.get("revenue"),        # 억원 단위
            "source":         "dart",
        }

    # ── 기업코드 조회 ────────────────────────────────────────────────────────

    def _get_corp_code(self, company_name: str) -> str | None:
        try:
            with httpx.Client(timeout=10) as client:
                res = client.get(
                    f"{DART_BASE}/company.json",
                    params={"crtfc_key": self.api_key, "corp_name": company_name},
                )
                res.raise_for_status()
                data = res.json()

            if data.get("status") != "000" or not data.get("list"):
                return None

            # 정확히 일치하는 기업명 우선
            for item in data["list"]:
                if item["corp_name"] == company_name:
                    return item["corp_code"]
            return data["list"][0]["corp_code"]

        except Exception as e:
            logger.error(f"[DART] 기업코드 조회 실패: {e}")
            return None

    # ── 공시 목록 ────────────────────────────────────────────────────────────

    def _get_filings(self, corp_code: str) -> list[dict]:
        try:
            bgn_de = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            with httpx.Client(timeout=10) as client:
                res = client.get(
                    f"{DART_BASE}/list.json",
                    params={
                        "crtfc_key":  self.api_key,
                        "corp_code":  corp_code,
                        "bgn_de":     bgn_de,
                        "page_count": 40,
                        "sort":       "date",
                        "sort_mth":   "desc",
                    },
                )
                res.raise_for_status()
                data = res.json()

            raw = data.get("list", []) if data.get("status") == "000" else []
            return [
                {
                    "title":      f.get("report_nm", ""),
                    "date":       f.get("rcept_dt", ""),
                    "event_type": _classify_event(f.get("report_nm", "")),
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f.get('rcept_no')}",
                }
                for f in raw
            ]
        except Exception as e:
            logger.error(f"[DART] 공시 조회 실패: {e}")
            return []

    # ── 재무 정보 ────────────────────────────────────────────────────────────

    def _get_financials(self, corp_code: str) -> dict:
        """사업보고서에서 매출액·임직원수 추출"""
        try:
            year = str(datetime.now().year - 1)
            with httpx.Client(timeout=10) as client:
                res = client.get(
                    f"{DART_BASE}/fnlttSinglAcntAll.json",
                    params={
                        "crtfc_key": self.api_key,
                        "corp_code": corp_code,
                        "bsns_year": year,
                        "reprt_code": "11011",  # 사업보고서
                        "fs_div":    "CFS",     # 연결재무제표
                    },
                )
                res.raise_for_status()
                data = res.json()

            items = data.get("list", [])
            revenue = _extract_account(items, "매출액")
            return {
                "revenue": _to_billion(revenue),   # 억원
                "employee_count": None,             # 별도 API 필요 시 확장
            }
        except Exception as e:
            logger.error(f"[DART] 재무정보 조회 실패: {e}")
            return {}


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _classify_event(title: str) -> str:
    t = title.lower()
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(k in t for k in keywords):
            return event_type
    return "other"


def _extract_account(items: list, account_name: str) -> int | None:
    for item in items:
        if item.get("account_nm") == account_name:
            try:
                return int(item.get("thstrm_amount", "0").replace(",", ""))
            except ValueError:
                return None
    return None


def _to_billion(amount: int | None) -> int | None:
    """원 → 억원 변환"""
    if amount is None:
        return None
    return round(amount / 1_0000_0000)


def _empty_result(company_name: str) -> dict:
    return {
        "corp_code":      None,
        "corp_name":      company_name,
        "filings":        [],
        "employee_count": None,
        "revenue":        None,
        "source":         "none",
    }
