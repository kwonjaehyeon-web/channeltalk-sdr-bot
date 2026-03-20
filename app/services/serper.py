"""
Serper API — Google 검색으로 기업 정보 수집
검색 종류: 최신 뉴스, 채용 공고, 기업 개요
"""

import os
import httpx
from loguru import logger

SERPER_API_URL = "https://google.serper.dev/search"


class SerperService:

    def __init__(self):
        self.api_key = os.environ.get("SERPER_API_KEY", "")
        if not self.api_key:
            logger.warning("SERPER_API_KEY 없음 — 검색 비활성화")

    def fetch_all(self, company_name: str) -> dict:
        """
        4가지 검색 결과 반환:
        - overview: 기업 개요 (사업, 서비스, 고객)
        - scale:    규모/투자 (매출, 투자유치, 임직원)
        - news:     최신 동향 (성장, 신규 서비스, 이슈)
        - jobs:     채용 공고 (CS/마케팅/운영 채용 시그널)
        """
        return {
            "overview": self._search(f'"{company_name}" 서비스 소개 주요 고객 사업'),
            "scale":    self._search(f'"{company_name}" 투자 유치 OR 매출 OR 임직원 OR 시리즈'),
            "news":     self._search(f'"{company_name}" 성장 OR 출시 OR 확장 OR 사용자 2024 2025'),
            "jobs":     self._search(f'"{company_name}" 채용 CS OR 고객서비스 OR 마케팅 OR 운영'),
        }

    def _search(self, query: str) -> list[dict]:
        if not self.api_key:
            return []

        try:
            resp = httpx.post(
                SERPER_API_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "gl": "kr", "hl": "ko", "num": 5},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", [])[:5]:
                results.append({
                    "title":   item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link":    item.get("link", ""),
                })
            return results

        except Exception as e:
            logger.error(f"[Serper] 검색 실패 ({query[:30]}...): {e}")
            return []
