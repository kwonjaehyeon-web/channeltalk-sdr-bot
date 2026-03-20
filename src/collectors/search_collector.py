"""
Serper API 기반 뉴스/기업정보 수집기
https://serper.dev — 구글 검색 결과를 JSON으로 반환
"""

import os
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


SERPER_URL = "https://google.serper.dev/search"


class SearchCollector:

    def __init__(self):
        self.api_key = os.environ.get("SERPER_API_KEY")
        if not self.api_key:
            logger.warning("SERPER_API_KEY 미설정 — 검색 수집 비활성화")

    def fetch(self, company_name: str) -> list[dict]:
        if not self.api_key:
            return []

        results = []

        # 최근 뉴스
        results.extend(self._search(f"{company_name} 뉴스", search_type="news"))

        # 인원수/조직 정보
        results.extend(self._search(f"{company_name} 임직원수 조직"))

        # DX/IT 투자 관련
        results.extend(self._search(f"{company_name} 디지털전환 IT투자 2024 2025"))

        return self._deduplicate(results)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _search(self, query: str, search_type: str = "search") -> list[dict]:
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "gl": "kr", "hl": "ko", "num": 10}

        endpoint = f"https://google.serper.dev/{search_type}" if search_type == "news" else SERPER_URL

        with httpx.Client(timeout=10) as client:
            res = client.post(endpoint, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()

        items = data.get("organic", data.get("news", []))
        return [
            {
                "source": "serper",
                "query": query,
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("link", ""),
                "date": item.get("date", ""),
            }
            for item in items
        ]

    def _deduplicate(self, results: list[dict]) -> list[dict]:
        seen_urls = set()
        unique = []
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique.append(r)
        return unique
