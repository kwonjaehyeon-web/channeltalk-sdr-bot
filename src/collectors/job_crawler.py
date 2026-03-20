"""
채용공고 크롤러
사이트별 독립 모듈 구조 → 한 사이트 변경이 나머지에 영향 없음
현재 구현: 사람인 (가장 데이터 풍부)
TODO: 잡코리아, 원티드 추가
"""

import re
import time
import random
from loguru import logger
from playwright.sync_api import sync_playwright


JOB_CATEGORIES = {
    "tech": ["개발", "엔지니어", "데이터", "AI", "클라우드", "인프라", "DevOps", "ML", "백엔드", "프론트엔드", "풀스택"],
    "dx": ["DX", "디지털전환", "디지털 전환", "IT기획", "IT 기획", "스마트팩토리"],
    "management": ["팀장", "본부장", "이사", "CTO", "CDO", "CPO", "VP", "Director", "Lead"],
    "data": ["데이터분석", "데이터 분석", "BI", "애널리스트", "사이언티스트"],
    "ops": ["운영", "CS", "고객", "물류", "총무", "인사", "HR"],
    "sales": ["영업", "세일즈", "BD", "사업개발", "마케팅"],
}


class JobCrawler:

    def fetch(self, company_name: str) -> list[dict]:
        """사람인에서 기업명으로 채용공고 수집"""
        results = []
        try:
            results.extend(self._fetch_saramin(company_name))
        except Exception as e:
            logger.error(f"[사람인] {company_name} 수집 실패: {e}")
        return results

    def _fetch_saramin(self, company_name: str) -> list[dict]:
        postings = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # User-Agent 설정
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })

            url = f"https://www.saramin.co.kr/zf_user/search?searchType=search&searchword={company_name}&go=&flag=n&searchMode=1&searchPram=1&main_count=10&tab_type=recruit"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # 봇 감지 방지: 랜덤 딜레이
            time.sleep(random.uniform(1.5, 3.0))

            items = page.query_selector_all(".item_recruit")
            for item in items[:20]:  # 최대 20개
                try:
                    title_el = item.query_selector(".job_tit a")
                    company_el = item.query_selector(".corp_name a")
                    date_el = item.query_selector(".job_date .date")
                    condition_els = item.query_selector_all(".job_condition span")

                    title = title_el.inner_text().strip() if title_el else ""
                    company = company_el.inner_text().strip() if company_el else ""
                    date = date_el.inner_text().strip() if date_el else ""
                    conditions = [el.inner_text().strip() for el in condition_els]

                    # 대상 기업 공고만 필터링
                    if company_name not in company and company not in company_name:
                        continue

                    postings.append({
                        "source": "saramin",
                        "title": title,
                        "company": company,
                        "date": date,
                        "conditions": conditions,
                        "category": _classify_job(title),
                        "is_management": _is_management_role(title),
                    })
                except Exception:
                    continue

            browser.close()

        logger.info(f"[사람인] {company_name}: {len(postings)}건 수집")
        return postings


# ─── TODO: 잡코리아 크롤러 ────────────────────────────────────────────────────
# class JobKoreaCrawler:
#     def fetch(self, company_name: str) -> list[dict]: ...


# ─── TODO: 원티드 API 크롤러 ──────────────────────────────────────────────────
# class WantedCrawler:
#     def fetch(self, company_name: str) -> list[dict]: ...


# ─── 유틸 ────────────────────────────────────────────────────────────────────

def _classify_job(title: str) -> str:
    for category, keywords in JOB_CATEGORIES.items():
        if any(k in title for k in keywords):
            return category
    return "other"


def _is_management_role(title: str) -> bool:
    management_keywords = ["팀장", "본부장", "이사", "CTO", "CDO", "CPO", "VP", "Director", "Lead", "Head"]
    return any(k in title for k in management_keywords)
