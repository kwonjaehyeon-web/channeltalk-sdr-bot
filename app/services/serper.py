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
        3가지 검색 결과 반환:
        - news: 최신 뉴스
        - jobs: 채용 공고
        - overview: 기업 개요
        """
        return {
            "news":     self._search(f"{company_name} 최신 뉴스 2024 2025"),
            "jobs":     self._search(f"{company_name} 채용 공고 구인"),
            "overview": self._search(f"{company_name} 기업 소개 사업 서비스"),
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
