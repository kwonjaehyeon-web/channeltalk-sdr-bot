"""
Notion API — 분석 결과 저장 + 채널톡 컨텍스트 페이지 읽기
"""

import os
import time
from datetime import datetime
from loguru import logger
import httpx

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
CONTEXT_CACHE_TTL = 3600  # 1시간


class NotionService:

    def __init__(self):
        self.token      = os.environ.get("NOTION_TOKEN", "")
        self.db_id      = os.environ.get("NOTION_DATABASE_ID", "")
        self.context_id = os.environ.get("NOTION_CONTEXT_PAGE_ID", "")
        self._context_cache: str = ""
        self._context_cached_at: float = 0

        if not self.token:
            logger.warning("NOTION_TOKEN 없음 — Notion 비활성화")
        if not self.context_id:
            logger.warning("NOTION_CONTEXT_PAGE_ID 없음 — 채널톡 컨텍스트 미사용")

    # ── 채널톡 컨텍스트 읽기 ────────────────────────────────────────────────────

    def fetch_channeltalk_context(self) -> str:
        """채널톡 SDR 컨텍스트 페이지를 읽어 텍스트로 반환 (1시간 캐시)"""
        if not self.token or not self.context_id:
            return ""

        now = time.time()
        if self._context_cache and (now - self._context_cached_at) < CONTEXT_CACHE_TTL:
            logger.debug("[Notion] 컨텍스트 캐시 사용")
            return self._context_cache

        try:
            text = self._read_page_blocks(self.context_id)
            self._context_cache = text
            self._context_cached_at = now
            logger.info("[Notion] 채널톡 컨텍스트 갱신 완료")
            return text
        except Exception as e:
            logger.error(f"[Notion] 컨텍스트 읽기 실패: {e}")
            return self._context_cache  # 실패 시 이전 캐시 사용

    def _read_page_blocks(self, page_id: str) -> str:
        """Notion 페이지 블록을 plain text로 변환"""
        resp = httpx.get(
            f"{NOTION_API_URL}/blocks/{page_id}/children",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
            },
            params={"page_size": 100},
            timeout=10,
        )
        resp.raise_for_status()
        blocks = resp.json().get("results", [])

        lines = []
        for block in blocks:
            text = self._block_to_text(block)
            if text:
                lines.append(text)
        return "\n".join(lines)

    def _block_to_text(self, block: dict) -> str:
        btype = block.get("type", "")
        content = block.get(btype, {})
        rich = content.get("rich_text", [])
        text = "".join(r.get("plain_text", "") for r in rich)

        if btype == "heading_1":
            return f"# {text}"
        if btype == "heading_2":
            return f"## {text}"
        if btype == "heading_3":
            return f"### {text}"
        if btype in ("paragraph", "bulleted_list_item", "numbered_list_item"):
            return text
        return ""

    def save(self, company_name: str, result: dict) -> str | None:
        """
        분석 결과를 Notion DB에 저장.
        반환: 생성된 페이지 URL (실패 시 None)
        """
        if not self.token or not self.db_id:
            logger.warning("[Notion] 토큰 또는 DB ID 없음 — 저장 건너뜀")
            return None

        try:
            page = self._create_page(company_name, result)
            url = page.get("url", "")
            logger.info(f"[Notion] 저장 완료: {url}")
            return url
        except Exception as e:
            logger.error(f"[Notion] 저장 실패: {e}")
            return None

    def _create_page(self, company_name: str, r: dict) -> dict:
        icp_fit = r.get("icp_fit", "Medium")
        icp_color = {"High": "green", "Medium": "yellow", "Low": "red"}.get(icp_fit, "default")

        payload = {
            "parent": {"database_id": self.db_id},
            "properties": {
                "기업명": {
                    "title": [{"text": {"content": company_name}}]
                },
                "산업": {
                    "rich_text": [{"text": {"content": r.get("icp_industry", "")}}]
                },
                "규모/매출": {
                    "rich_text": [{"text": {"content": r.get("icp_scale", "")}}]
                },
                "ICP 적합도": {
                    "select": {"name": icp_fit, "color": icp_color}
                },
                "문제 (Problem)": {
                    "rich_text": [{"text": {"content": r.get("problem", "")}}]
                },
                "채널톡 솔루션": {
                    "rich_text": [{"text": {"content": r.get("channeltalk_solution", "")}}]
                },
                "의사결정자": {
                    "rich_text": [{"text": {"content": r.get("decision_maker", "")}}]
                },
                "분석일시": {
                    "date": {"start": datetime.now().strftime("%Y-%m-%d")}
                },
            },
            "children": [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": "기업 요약"}}]},
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": r.get("company_summary", "")}}]},
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": "문제 근거"}}]},
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": r.get("problem_evidence", "")}}]},
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": "ICP 판단 근거"}}]},
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": r.get("icp_fit_reason", "")}}]},
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": "의사결정자 추론 근거"}}]},
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": r.get("decision_maker_reason", "")}}]},
                },
            ],
        }

        resp = httpx.post(
            f"{NOTION_API_URL}/pages",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
